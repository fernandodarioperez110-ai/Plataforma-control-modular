/*
 * BallAndBeam_Web.ino
 * -----------------------------------------------------------------------
 * Firmware unificado para conectar el balancín (Ball and Beam) real con la
 * aplicación web "flujo_controlador_ESP32".
 *
 * IMPORTANTE: la lógica de cada controlador es la MISMA que en tus sketches
 * individuales (BallAndBeam_PID.ino, _Difusa.ino, _LQR.ino, _SMC.ino),
 * copiada tal cual. Lo único que cambia es que, en vez de tener los
 * parámetros fijos como "const" en el código, se reciben desde la web con
 * el mismo nombre y orden que usabas en Arduino IDE:
 *
 *   pid    : setpoint, kp, ki, kd
 *   difusa : setpoint, E_PICOS[1..7], DE_PICOS[1..7], SALIDA_PICOS[1..7]
 *   lqr    : setpoint, k1, k2
 *   smc    : setpoint, lambda, k_smc (eta), phi
 *
 * Protocolo con el backend (ver backend/source.py, Esp32SerialSource):
 *   PC -> ESP32 :  START,<controlador>,<p1>,<p2>,...\n
 *                  STOP\n
 *   ESP32 -> PC :  DATA,<t>,<ref>,<vc>,<error>,<u>\n     (una vez por ciclo)
 *                  DONE\n                                (al terminar solo)
 *
 * El backend en modo hardware real (USE_SIMULATOR=False) NO calcula nada:
 * solo reenvía lo que el ESP32 reporta. Todo el control vive aquí.
 *
 * Diferencia respecto a usar cada sketch por separado: aquí "setpoint" es
 * un solo valor objetivo (error = setpoint - distancia), en vez de la banda
 * [SETPOINT_MIN, SETPOINT_MAX] de los sketches originales. El resto de la
 * física/filtros/fórmulas es idéntico.
 *
 * Hardware (igual que tus sketches individuales):
 *   - Sensor IR Sharp GP2Y0A21YK0F  -> GPIO 1 (ADC)
 *   - Servo (viga)                  -> GPIO 4, librería ESP32Servo
 * -----------------------------------------------------------------------
 */

#include <ESP32Servo.h>

// ==========================================================================
//  HARDWARE / CALIBRACIÓN (idéntico a los sketches originales)
// ==========================================================================
const int PIN_SERVO      = 4;
const int PIN_SENSOR_IR  = 1;

const float DIST_MIN_FISICA = 12.0;   // cm - más cerca posible del sensor
const float DIST_MAX_FISICA = 60.0;   // cm - más lejos posible del sensor
const float DIST_MAX_VALIDA = 70.0;   // cm - margen de validación del sensor

const int   SERVO_MIN    = 10;    // grados, límite mecánico
const int   SERVO_MAX    = 90;    // grados, límite mecánico
const float SERVO_CENTRO = 35.0;  // grados, ángulo de nivel (bola quieta)

// Calibración sensor Sharp GP2Y0A21YK0F: distancia_cm = A * voltage^B
const float CAL_A = 27.86;
const float CAL_B = -1.15;
const float ADC_MAX_CUENTA = 4095.0;
const float ADC_VREF       = 3.3;

const float ALPHA_FILTRO_POS = 0.25;  // EMA para posición (PID/Difusa usan ALPHA_FILTRO)
const float ALPHA_FILTRO_VEL = 0.20;  // EMA para velocidad estimada (LQR/SMC)

const unsigned long TS_MS = 30;       // periodo de muestreo, igual a los sketches originales
const float TS_S = TS_MS / 1000.0;

// Física real del balancín (para LQR y SMC), igual a BallAndBeam_LQR.ino / _SMC.ino
// aceleracion_bola =~ (5/7)*g*alpha  (alpha en radianes)
const float B_CONST = (5.0 / 7.0) * 9.81;

// ==========================================================================
//  PROTOCOLO WEB: tolerancia / fin de corrida (igual a backend/source.py)
// ==========================================================================
const float MAX_T        = 25.0;  // segundos, tope de duración de una corrida
const float TOL_STEADY_S = 1.0;   // segundos que el error debe permanecer dentro de tolerancia
// tolerancia = max(0.02*|setpoint|, 0.3)  (mismo criterio que el backend)

Servo servoViga;

// ==========================================================================
//  ESTADO GLOBAL
// ==========================================================================
enum Controlador { NINGUNO, PID_C, DIFUSA_C, LQR_C, SMC_C };

bool corriendo = false;
Controlador controladorActivo = NINGUNO;

float setpoint = 31.0;   // cm, posición deseada de la bola

// --- parámetros PID (= Kp, Ki, Kd de BallAndBeam_PID.ino) ---
float pid_kp = 0, pid_ki = 0, pid_kd = 0;
float pid_integral = 0;
float pid_errorAnterior = 0;
const float PID_LIMITE_INTEGRAL = 15.0;  // = LIMITE_INTEGRAL del sketch original

// --- parámetros Difusa (= E_PICOS/DE_PICOS/SALIDA_PICOS de BallAndBeam_Difusa.ino) ---
const int N_ETIQUETAS = 7;
float fz_ePicos[N_ETIQUETAS];
float fz_dePicos[N_ETIQUETAS];
float fz_salidaPicos[N_ETIQUETAS];
float fz_errorAnterior = 0;

// --- parámetros LQR (= K1, K2 de BallAndBeam_LQR.ino) ---
float lqr_k1 = 0, lqr_k2 = 0;

// --- parámetros SMC (= LAMBDA, K_SMC, PHI de BallAndBeam_SMC.ino) ---
float smc_lambda = 0, smc_kSmc = 0, smc_phi = 0;

// --- estado común de planta (posición/velocidad estimadas) ---
float distanciaFiltrada = 0;
float velocidadFiltrada = 0;
float distanciaAnterior = 0;
bool  primeraLectura = true;

// --- control de tiempo de la corrida ---
unsigned long tInicioMs = 0;
unsigned long tUltimoCicloMs = 0;
float tiempoDentroToleranciaS = 0;

// ==========================================================================
//  SETUP
// ==========================================================================
void setup() {
  Serial.begin(115200);
  delay(200);

  analogReadResolution(12);
  analogSetPinAttenuation(PIN_SENSOR_IR, ADC_11db);

  ESP32PWM::allocateTimer(0);
  servoViga.setPeriodHertz(50);
  servoViga.attach(PIN_SERVO, 500, 2400);
  servoViga.write((int)SERVO_CENTRO);
  delay(500);

  // Primera lectura para inicializar el filtro
  distanciaFiltrada = leerDistanciaCm();
  distanciaAnterior = distanciaFiltrada;
}

// ==========================================================================
//  LOOP PRINCIPAL
// ==========================================================================
void loop() {
  procesarSerial();

  if (!corriendo) {
    return;
  }

  unsigned long ahora = millis();
  if (ahora - tUltimoCicloMs < TS_MS) {
    return;
  }
  tUltimoCicloMs = ahora;

  actualizarSensor();

  float error = setpoint - distanciaFiltrada;
  float u = 0;  // salida de control, grados de offset respecto a SERVO_CENTRO

  switch (controladorActivo) {
    case PID_C:    u = calcularPID(error);             break;
    case DIFUSA_C: u = calcularDifusa(error);           break;
    case LQR_C:    u = calcularLQR(distanciaFiltrada);  break;
    case SMC_C:    u = calcularSMC(distanciaFiltrada);  break;
    default:       u = 0;                               break;
  }

  aplicarServo(u);

  float tS = (ahora - tInicioMs) / 1000.0;

  // Reporte de telemetría al backend: DATA,<t>,<ref>,<vc>,<error>,<u>
  Serial.print("DATA,");
  Serial.print(tS, 3);
  Serial.print(",");
  Serial.print(setpoint, 3);
  Serial.print(",");
  Serial.print(distanciaFiltrada, 3);
  Serial.print(",");
  Serial.print(error, 3);
  Serial.print(",");
  Serial.println(constrain(u, -100.0, 100.0), 3);

  // --- detección de fin de corrida (igual criterio que el backend) ---
  float tolerancia = max(0.02 * fabs(setpoint), 0.3);
  if (fabs(error) <= tolerancia) {
    tiempoDentroToleranciaS += TS_S;
  } else {
    tiempoDentroToleranciaS = 0;
  }

  bool terminoPorEstabilidad = (tiempoDentroToleranciaS >= TOL_STEADY_S);
  bool terminoPorTiempo = (tS >= MAX_T);

  if (terminoPorEstabilidad || terminoPorTiempo) {
    finalizarCorrida();
  }
}

// ==========================================================================
//  MANEJO DE COMANDOS SERIAL (START / STOP), no bloqueante
// ==========================================================================
void procesarSerial() {
  while (Serial.available() > 0) {
    String linea = Serial.readStringUntil('\n');
    linea.trim();
    if (linea.length() == 0) continue;

    if (linea.startsWith("START")) {
      manejarStart(linea);
    } else if (linea.startsWith("STOP")) {
      manejarStop();
    }
  }
}

void manejarStart(String linea) {
  // Formato: START,<controlador>,<p1>,<p2>,...
  // Difusa necesita el máximo de tokens: START,difusa,setpoint,e1..7,de1..7,s1..7 = 24
  const int MAX_TOKENS = 28;
  String tokens[MAX_TOKENS];
  int n = dividirCSV(linea, tokens, MAX_TOKENS);
  if (n < 2) return;  // línea mal formada

  String idControlador = tokens[1];
  idControlador.toLowerCase();

  bool ok = true;

  if (idControlador == "pid") {
    // setpoint, kp, ki, kd
    if (n < 6) { ok = false; }
    else {
      setpoint = tokens[2].toFloat();
      pid_kp   = tokens[3].toFloat();
      pid_ki   = tokens[4].toFloat();
      pid_kd   = tokens[5].toFloat();
      pid_integral = 0;
      pid_errorAnterior = 0;
      controladorActivo = PID_C;
    }
  } else if (idControlador == "difusa") {
    // setpoint, e1..e7, de1..de7, s1..s7  (22 valores)
    if (n < 24) { ok = false; }
    else {
      setpoint = tokens[2].toFloat();
      for (int i = 0; i < N_ETIQUETAS; i++) fz_ePicos[i]      = tokens[3 + i].toFloat();
      for (int i = 0; i < N_ETIQUETAS; i++) fz_dePicos[i]     = tokens[10 + i].toFloat();
      for (int i = 0; i < N_ETIQUETAS; i++) fz_salidaPicos[i] = tokens[17 + i].toFloat();
      fz_errorAnterior = 0;
      controladorActivo = DIFUSA_C;
    }
  } else if (idControlador == "lqr") {
    // setpoint, k1, k2
    if (n < 5) { ok = false; }
    else {
      setpoint = tokens[2].toFloat();
      lqr_k1   = tokens[3].toFloat();
      lqr_k2   = tokens[4].toFloat();
      controladorActivo = LQR_C;
    }
  } else if (idControlador == "smc") {
    // setpoint, lambda, eta (k_smc), phi
    if (n < 6) { ok = false; }
    else {
      setpoint   = tokens[2].toFloat();
      smc_lambda = tokens[3].toFloat();
      smc_kSmc   = tokens[4].toFloat();
      smc_phi    = tokens[5].toFloat();
      controladorActivo = SMC_C;
    }
  } else {
    ok = false;
  }

  if (!ok) {
    controladorActivo = NINGUNO;
    return;
  }

  // Reiniciar estado de la corrida
  primeraLectura = true;
  distanciaFiltrada = leerDistanciaCm();
  distanciaAnterior = distanciaFiltrada;
  velocidadFiltrada = 0;
  tiempoDentroToleranciaS = 0;
  tInicioMs = millis();
  tUltimoCicloMs = tInicioMs;
  corriendo = true;
}

void manejarStop() {
  corriendo = false;
  controladorActivo = NINGUNO;
  servoViga.write((int)SERVO_CENTRO);
}

void finalizarCorrida() {
  corriendo = false;
  controladorActivo = NINGUNO;
  servoViga.write((int)SERVO_CENTRO);
  Serial.println("DONE");
}

// Separador CSV simple; devuelve el número de tokens encontrados
int dividirCSV(String s, String* tokens, int maxTokens) {
  int count = 0;
  int start = 0;
  while (count < maxTokens) {
    int idx = s.indexOf(',', start);
    if (idx == -1) {
      tokens[count++] = s.substring(start);
      break;
    }
    tokens[count++] = s.substring(start, idx);
    start = idx + 1;
  }
  return count;
}

// ==========================================================================
//  SENSOR: lectura + filtro EMA de posición y velocidad
//  (idéntico a leerDistanciaCM() de tus sketches originales)
// ==========================================================================
float leerDistanciaCm() {
  int lectura = analogRead(PIN_SENSOR_IR);
  float voltaje = (lectura / ADC_MAX_CUENTA) * ADC_VREF;
  if (voltaje < 0.1) voltaje = 0.1;

  float distanciaCruda = CAL_A * pow(voltaje, CAL_B);

  if (distanciaCruda > DIST_MAX_VALIDA) {
    return distanciaFiltrada;  // lectura no confiable: conserva el último valor filtrado
  }

  float distancia = constrain(distanciaCruda, DIST_MIN_FISICA, DIST_MAX_FISICA);
  return distancia;
}

void actualizarSensor() {
  float distanciaCruda = leerDistanciaCm();

  if (primeraLectura) {
    distanciaFiltrada = distanciaCruda;
    distanciaAnterior = distanciaCruda;
    velocidadFiltrada = 0;
    primeraLectura = false;
    return;
  }

  float distanciaPrev = distanciaFiltrada;
  distanciaFiltrada = ALPHA_FILTRO_POS * distanciaCruda + (1 - ALPHA_FILTRO_POS) * distanciaFiltrada;

  float velocidadCruda = (distanciaFiltrada - distanciaPrev) / TS_S;
  velocidadFiltrada = ALPHA_FILTRO_VEL * velocidadCruda + (1 - ALPHA_FILTRO_VEL) * velocidadFiltrada;
}

// ==========================================================================
//  ACTUACIÓN: u (grados de offset) -> ángulo real de servo, con límites
// ==========================================================================
void aplicarServo(float u) {
  float anguloServo = SERVO_CENTRO + u;
  anguloServo = constrain(anguloServo, SERVO_MIN, SERVO_MAX);
  servoViga.write((int)anguloServo);
}

// ==========================================================================
//  CONTROLADOR 1: PID  — idéntico a BallAndBeam_PID.ino
// ==========================================================================
float calcularPID(float error) {
  // Reinicio de integral si el error cambia de signo (igual al sketch original)
  if ((error >= 0 && pid_errorAnterior < 0) || (error <= 0 && pid_errorAnterior > 0)) {
    pid_integral = 0;
  }

  float derivada = (error - pid_errorAnterior) / TS_S;
  pid_errorAnterior = error;

  // Anti-windup por integración condicional (igual al sketch original)
  float anguloPrevio = SERVO_CENTRO + (pid_kp * error) + (pid_kd * derivada) + (pid_ki * pid_integral);
  bool saturadoAlto = anguloPrevio >= SERVO_MAX;
  bool saturadoBajo = anguloPrevio <= SERVO_MIN;

  if (!(saturadoAlto && error > 0) && !(saturadoBajo && error < 0)) {
    pid_integral += error * TS_S;
    pid_integral = constrain(pid_integral, -PID_LIMITE_INTEGRAL, PID_LIMITE_INTEGRAL);
  }

  float u = (pid_kp * error) + (pid_ki * pid_integral) + (pid_kd * derivada);
  return u;
}

// ==========================================================================
//  CONTROLADOR 2: DIFUSA — idéntico a BallAndBeam_Difusa.ino
//  (Mamdani, 7 etiquetas NL..PL, 49 reglas vía idx_salida = idxE+idxDE-3,
//  defuzzificación por promedio ponderado)
// ==========================================================================
void fuzzificar(float x, const float picos[], int idx[2], float grado[2]) {
  if (x <= picos[0]) {
    idx[0] = 0; grado[0] = 1.0;
    idx[1] = 0; grado[1] = 0.0;
    return;
  }
  if (x >= picos[N_ETIQUETAS - 1]) {
    idx[0] = N_ETIQUETAS - 1; grado[0] = 1.0;
    idx[1] = N_ETIQUETAS - 1; grado[1] = 0.0;
    return;
  }
  for (int k = 0; k < N_ETIQUETAS - 1; k++) {
    if (x >= picos[k] && x <= picos[k + 1]) {
      float rango = picos[k + 1] - picos[k];
      float gradoSuperior = (x - picos[k]) / rango;
      float gradoInferior = 1.0 - gradoSuperior;
      idx[0] = k;     grado[0] = gradoInferior;
      idx[1] = k + 1; grado[1] = gradoSuperior;
      return;
    }
  }
}

float calcularDifusa(float error) {
  float derivadaError = (error - fz_errorAnterior) / TS_S;
  fz_errorAnterior = error;

  int idxE[2], idxDE[2];
  float gradoE[2], gradoDE[2];

  fuzzificar(error, fz_ePicos, idxE, gradoE);
  fuzzificar(derivadaError, fz_dePicos, idxDE, gradoDE);

  float numerador = 0.0;
  float denominador = 0.0;

  for (int a = 0; a < 2; a++) {
    if (gradoE[a] <= 0.0) continue;
    for (int b = 0; b < 2; b++) {
      if (gradoDE[b] <= 0.0) continue;

      float disparo = min(gradoE[a], gradoDE[b]);

      int idxSalida = idxE[a] + idxDE[b] - 3;
      idxSalida = constrain(idxSalida, 0, N_ETIQUETAS - 1);

      numerador   += disparo * fz_salidaPicos[idxSalida];
      denominador += disparo;
    }
  }

  if (denominador <= 0.0) return 0.0;
  return numerador / denominador;
}

// ==========================================================================
//  CONTROLADOR 3: LQR — idéntico a BallAndBeam_LQR.ino
//  u = -(K1*x1 + K2*x2), x1/x2 en METROS y m/s (igual que el sketch original)
// ==========================================================================
float calcularLQR(float distanciaCm) {
  float x1 = (distanciaCm - setpoint) / 100.0;   // posición (m)
  float x2 = velocidadFiltrada / 100.0;           // velocidad (m/s)

  float thetaRad = -(lqr_k1 * x1 + lqr_k2 * x2);
  float thetaDeg = thetaRad * RAD_TO_DEG;
  return thetaDeg;
}

// ==========================================================================
//  CONTROLADOR 4: SMC — idéntico a BallAndBeam_SMC.ino
//  x1/x2 en METROS y m/s (igual que el sketch original)
// ==========================================================================
float calcularSMC(float distanciaCm) {
  float x1 = (distanciaCm - setpoint) / 100.0;   // error de posición (m)
  float x2 = velocidadFiltrada / 100.0;           // velocidad (m/s)

  float s = x2 + smc_lambda * x1;
  float satS = constrain(s / smc_phi, -1.0, 1.0);

  float alphaRad = -(smc_lambda * x2 + smc_kSmc * satS) / B_CONST;
  float alphaDeg = alphaRad * RAD_TO_DEG;
  return alphaDeg;
}

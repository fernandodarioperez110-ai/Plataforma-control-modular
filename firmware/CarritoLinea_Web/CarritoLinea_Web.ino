/*
  ============================================================================
  CARRITO SEGUIDOR DE LINEA - FIRMWARE PARA LA APP WEB DEL PROYECTO (ESP32-S3)
  ============================================================================
  Proyecto: DARIO PROGRAMACION - Plataforma experimental (segundo prototipo)

  Une en un solo sketch los 4 controladores MEJORADOS del carrito, con la
  MISMA logica que los sketches individuales ya probados en la pista:
    pid    -> CarritoLinea_PID_Mejorado.ino
    difusa -> CarritoLinea_Difusa_Mejorado.ino
    lqr    -> CarritoLinea_LQR_Mejorado.ino   (+ observador de estados)
    smc    -> CarritoLinea_SMC_Mejorado.ino   (+ observador de estados)
  Los parametros ya no estan fijos: llegan desde la app web en cada corrida.

  CONEXION CON LA APP (igual que las paginas de prueba de cada controlador):
    El ESP32 crea su propia red WiFi y la app le habla con peticiones HTTP
    cortas (pregunta y respuesta). Si una peticion se pierde, la siguiente
    funciona igual; no hay una conexion continua que se pueda "romper".

    Red: "ESP32-CARRITO" (contrasena 12345678)   IP: 192.168.5.1
    (la IP coincide con ESP32_IPS["carrito"] en backend/main.py)

    GET /iniciar?ctrl=pid&base=180&kp=100&ki=0&kd=0.5
        ctrl = pid | difusa | lqr | smc, y los parametros de ese
        controlador por nombre (los mismos de backend/controllers.py).
    GET /detener
    GET /datos?desde=N
        Devuelve las muestras guardadas a partir de la numero N:
        {"total":..,"corriendo":..,"fin":"..","m":[[t,ref,vc,error,u],...]}
          t     = tiempo desde INICIAR (s)
          ref   = referencia: 0 (linea centrada)
          vc    = posicion de la linea bajo los sensores (cm)
          error = ref - vc (cm)
          u     = correccion entre motores (PWM)
        fin = "" (corriendo) | "manual" | "tiempo" | "linea" | "conexion"

  Fin de una corrida:
    - "manual":   se pulso Finalizar en la app.
    - "tiempo":   se cumplio DURACION_CORRIDA_S.
    - "linea":    la linea estuvo perdida mas de 1 s (se salio de la pista).
    - "conexion": la app dejo de preguntar mas de TIEMPO_SIN_APP_MS
                  (seguridad: el carrito no sigue andando solo).

  Conexiones (segun "Diagrama Electrico Carrito"), motores y sentido de
  giro: IGUALES a los sketches mejorados.

  Librerias: ninguna adicional (WiFi.h y WebServer.h vienen con el nucleo
  ESP32 by Espressif 3.x).   Monitor Serial: 115200 baudios.
  ============================================================================
*/

#include <WiFi.h>
#include <WebServer.h>

// Declaracion de funciones
float leerPosicionLinea(unsigned long ahora);
void  fuzzificar(float x, const float picos[], int idx[2], float grado[2]);
float calcularDifusa(float error, float derivada);
void  escribirMotor(int pinIn1, int pinIn2, int pinPwm, int velocidad);
void  detenerMotores();
void  terminarCorrida(const char* motivo);
void  guardarMuestra(float t, float vc, float err, float u);
void  pedirIniciar();
void  pedirDetener();
void  pedirDatos();
void  paginaEstado();
float argFloat(const char* nombre, float porDefecto);

// ----------------------------------------------------------------------------
// PINES (iguales a los sketches mejorados)
// ----------------------------------------------------------------------------
const int PINES_SENSOR[5] = { 1, 2, 4, 5, 6 };   // OUT1 (izq) ... OUT5 (der)

const int PIN_PWMA = 7;    // canal A: velocidad
const int PIN_AIN1 = 8;    // canal A: direccion
const int PIN_AIN2 = 9;
const int PIN_STBY = 10;   // habilita el driver
const int PIN_BIN1 = 11;   // canal B: direccion
const int PIN_BIN2 = 12;
const int PIN_PWMB = 13;   // canal B: velocidad

// ----------------------------------------------------------------------------
// SENSORES
// ----------------------------------------------------------------------------
const int   NIVEL_LINEA = LOW;                          // LOW = negro
const float PESOS[5] = { -2.0, -1.0, 0.0, 1.0, 2.0 };
const float POSICION_LINEA_PERDIDA = 2.5;
const unsigned long TIEMPO_MAX_PERDIDA_MS = 1000;

// ----------------------------------------------------------------------------
// MOTORES (iguales a los sketches mejorados)
// ----------------------------------------------------------------------------
const int PWM_FRECUENCIA_HZ   = 20000;
const int PWM_RESOLUCION_BITS = 8;
const int PWM_MAX = 255;

const bool PERMITIR_REVERSA   = true;
const bool INVERTIR_MOTOR_IZQ = true;    // "izquierdo" = canal A
const bool INVERTIR_MOTOR_DER = false;   // "derecho"   = canal B
const int  SENTIDO_GIRO       = -1;

// Compensacion de motores (Prueba_Velocidad: recto con A=255, B=165)
const float FACTOR_MOTOR_A = 1.0;
const float FACTOR_MOTOR_B = 165.0 / 255.0;

// ----------------------------------------------------------------------------
// MODELO DEL CARRITO (medido el 05/10/2026, usado por LQR y SMC)
// ----------------------------------------------------------------------------
const float VEL_MAX_CM_S    = 11.2;
const float ANCHO_EJES_CM   = 8.0;
const float DIST_SENSOR_CM  = 7.0;
const float SEP_SENSORES_CM = 2.2;

// Observador de estados (igual que LQR/SMC mejorados)
const float POLO_OBSERVADOR = 4.0;
const float LIMITE_X2_RAD   = 0.5;

// ----------------------------------------------------------------------------
// CORRIDA
// ----------------------------------------------------------------------------
const unsigned long TS_MS = 20;               // 50 Hz
const float SETPOINT = 0.0;
const float DURACION_CORRIDA_S = 25.0;        // tope de cada corrida
const unsigned long TIEMPO_SIN_APP_MS = 3000; // seguridad si la app deja de preguntar

// ----------------------------------------------------------------------------
// WIFI
// ----------------------------------------------------------------------------
const char* AP_SSID = "ESP32-CARRITO";
const char* AP_PASS = "12345678";
const IPAddress IP_AP     (192, 168, 5, 1);
const IPAddress IP_SUBRED (255, 255, 255, 0);

WebServer server(80);

// ----------------------------------------------------------------------------
// PARAMETROS (llegan desde la app; estos son los valores por defecto,
// iguales a los de los sketches mejorados)
// ----------------------------------------------------------------------------
enum Controlador { NINGUNO, PID_C, DIFUSA_C, LQR_C, SMC_C };
Controlador controlador = NINGUNO;
const char* nombreCtrl = "";

int   velocidadBase = 180;

float Kp = 100.0, Ki = 0.0, Kd = 0.5;
const float LIMITE_INTEGRAL = 2.0;

const int N_ETIQUETAS = 7;
float E_PICOS[N_ETIQUETAS]      = { -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0 };
float DE_PICOS[N_ETIQUETAS]     = { -45.0, -30.0, -15.0, 0.0, 15.0, 30.0, 45.0 };
float SALIDA_PICOS[N_ETIQUETAS] = { -220.0, -140.0, -80.0, 0.0, 80.0, 140.0, 220.0 };
const float ALPHA_DERIVADA = 0.3;

float K1 = 45.4545, K2 = 194.9067;

float LAMBDA = 3.0, K_SMC = 32.0, PHI = 6.6;

// ----------------------------------------------------------------------------
// ESTADO
// ----------------------------------------------------------------------------
bool corriendo = false;
const char* motivoFin = "";
unsigned long inicioMs = 0, tiempoAnterior = 0, ultimaPeticionMs = 0;

// PID / Difusa
float errorAnterior = 0.0, integral = 0.0, derivadaFiltrada = 0.0;
bool  primeraMuestra = true;

// Observador (LQR / SMC)
float vAvance = 0.0, gGiro = 0.0, lObs1 = 0.0, lObs2 = 0.0;
float x1Est = 0.0, x2Est = 0.0, uAnterior = 0.0;

// Sensores
float ultimaPosicionValida = 0.0;
bool  lineaVisible = true;
unsigned long inicioPerdidaMs = 0;
float posicionActual = 0.0;

// Buffer de muestras para la app (12 s a 50 Hz)
struct Muestra { float t, vc, err, u; };
const int TAM_BUFFER = 600;
Muestra buffer[TAM_BUFFER];
unsigned long totalMuestras = 0;

// ----------------------------------------------------------------------------
// SETUP
// ----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(200);

  for (int i = 0; i < 5; i++) pinMode(PINES_SENSOR[i], INPUT);
  pinMode(PIN_AIN1, OUTPUT); pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_BIN1, OUTPUT); pinMode(PIN_BIN2, OUTPUT);
  pinMode(PIN_STBY, OUTPUT);
  digitalWrite(PIN_STBY, LOW);

  ledcAttach(PIN_PWMA, PWM_FRECUENCIA_HZ, PWM_RESOLUCION_BITS);
  ledcAttach(PIN_PWMB, PWM_FRECUENCIA_HZ, PWM_RESOLUCION_BITS);
  detenerMotores();

  WiFi.mode(WIFI_AP);
  WiFi.setSleep(false);
  WiFi.softAPConfig(IP_AP, IP_AP, IP_SUBRED);
  WiFi.softAP(AP_SSID, AP_PASS);
  server.on("/", paginaEstado);
  server.on("/iniciar", pedirIniciar);
  server.on("/detener", pedirDetener);
  server.on("/datos", pedirDatos);
  server.begin();

  Serial.println("Carrito seguidor de linea - firmware para la app web");
  Serial.print("Red WiFi: "); Serial.println(AP_SSID);
  Serial.print("IP: ");       Serial.println(WiFi.softAPIP());
  tiempoAnterior = millis();
}

// ----------------------------------------------------------------------------
// LOOP
// ----------------------------------------------------------------------------
void loop() {
  server.handleClient();

  unsigned long ahora = millis();
  if (ahora - tiempoAnterior < TS_MS) return;
  float dt = (ahora - tiempoAnterior) / 1000.0;
  tiempoAnterior = ahora;

  posicionActual = leerPosicionLinea(ahora);
  if (!corriendo) { detenerMotores(); return; }

  float t = (ahora - inicioMs) / 1000.0;

  // --- Condiciones de fin ---
  if (!lineaVisible && (ahora - inicioPerdidaMs) > TIEMPO_MAX_PERDIDA_MS) { terminarCorrida("linea"); return; }
  if (t >= DURACION_CORRIDA_S)                                            { terminarCorrida("tiempo"); return; }
  if (ahora - ultimaPeticionMs > TIEMPO_SIN_APP_MS)                       { terminarCorrida("conexion"); return; }

  // --- Controlador elegido ---
  float error = SETPOINT - posicionActual;
  float correccion = 0.0;

  if (controlador == PID_C) {
    // ===== PID (igual que CarritoLinea_PID_Mejorado) =====
    float derivada = 0.0;
    if (!primeraMuestra) derivada = (error - errorAnterior) / dt;
    primeraMuestra = false;
    if ((error > 0 && errorAnterior < 0) || (error < 0 && errorAnterior > 0)) integral = 0.0;
    float previa = Kp * error + Ki * integral + Kd * derivada;
    bool saturado = fabs(previa) >= PWM_MAX;
    if (!saturado || (previa * error) < 0) {
      integral += error * dt;
      integral = constrain(integral, -LIMITE_INTEGRAL, LIMITE_INTEGRAL);
    }
    errorAnterior = error;
    correccion = SENTIDO_GIRO * (Kp * error + Ki * integral + Kd * derivada);

  } else if (controlador == DIFUSA_C) {
    // ===== Difusa (igual que CarritoLinea_Difusa_Mejorado) =====
    float derivadaCruda = 0.0;
    if (!primeraMuestra) derivadaCruda = (error - errorAnterior) / dt;
    primeraMuestra = false;
    errorAnterior = error;
    derivadaFiltrada = ALPHA_DERIVADA * derivadaCruda + (1.0 - ALPHA_DERIVADA) * derivadaFiltrada;
    correccion = SENTIDO_GIRO * calcularDifusa(error, derivadaFiltrada);

  } else {
    // ===== LQR y SMC: observador de estados (igual que los mejorados) =====
    float x1Medido = posicionActual * SEP_SENSORES_CM;
    float x1Pred = x1Est + dt * (vAvance * x2Est + DIST_SENSOR_CM * gGiro * uAnterior);
    float x2Pred = x2Est + dt * (gGiro * uAnterior);
    float innovacion = x1Medido - x1Pred;
    x1Est = x1Pred + dt * lObs1 * innovacion;
    x2Est = x2Pred + dt * lObs2 * innovacion;
    x2Est = constrain(x2Est, -LIMITE_X2_RAD, LIMITE_X2_RAD);

    float u;
    if (controlador == LQR_C) {
      u = -(K1 * x1Est + K2 * x2Est);
    } else {
      float s = LAMBDA * x1Est + vAvance * x2Est;
      float satS = constrain(s / PHI, -1.0, 1.0);
      float denominador = (LAMBDA * DIST_SENSOR_CM + vAvance) * gGiro;
      u = -(LAMBDA * vAvance * x2Est + K_SMC * satS) / denominador;
    }
    u = constrain(u, -2.0 * PWM_MAX, 2.0 * PWM_MAX);
    correccion = SENTIDO_GIRO * u;
  }

  // --- Motores ---
  int velMin = PERMITIR_REVERSA ? -PWM_MAX : 0;
  int velIzq = constrain((int)(velocidadBase - correccion), velMin, PWM_MAX);
  int velDer = constrain((int)(velocidadBase + correccion), velMin, PWM_MAX);
  // El observador usa la senal que de verdad llega a los motores
  uAnterior = SENTIDO_GIRO * (velDer - velIzq) / 2.0;

  int pwmA = (int)(velIzq * FACTOR_MOTOR_A);
  int pwmB = (int)(velDer * FACTOR_MOTOR_B);
  escribirMotor(PIN_AIN1, PIN_AIN2, PIN_PWMA, INVERTIR_MOTOR_IZQ ? -pwmA : pwmA);
  escribirMotor(PIN_BIN1, PIN_BIN2, PIN_PWMB, INVERTIR_MOTOR_DER ? -pwmB : pwmB);

  // --- Muestra para la app (en cm, igual que la unidad del prototipo) ---
  float vc = posicionActual * SEP_SENSORES_CM;
  guardarMuestra(t, vc, SETPOINT - vc, correccion);
}

// ----------------------------------------------------------------------------
// SENSORES (igual que los sketches mejorados)
// ----------------------------------------------------------------------------
float leerPosicionLinea(unsigned long ahora) {
  float suma = 0.0; int activos = 0;
  for (int i = 0; i < 5; i++) {
    if (digitalRead(PINES_SENSOR[i]) == NIVEL_LINEA) { suma += PESOS[i]; activos++; }
  }
  if (activos == 0) {
    if (lineaVisible) inicioPerdidaMs = ahora;
    lineaVisible = false;
    if (ultimaPosicionValida < 0) return -POSICION_LINEA_PERDIDA;
    if (ultimaPosicionValida > 0) return  POSICION_LINEA_PERDIDA;
    return 0.0;
  }
  lineaVisible = true;
  ultimaPosicionValida = suma / activos;
  return ultimaPosicionValida;
}

// ----------------------------------------------------------------------------
// LOGICA DIFUSA (igual que CarritoLinea_Difusa_Mejorado)
// ----------------------------------------------------------------------------
void fuzzificar(float x, const float picos[], int idx[2], float grado[2]) {
  if (x <= picos[0]) { idx[0] = 0; grado[0] = 1.0; idx[1] = 0; grado[1] = 0.0; return; }
  if (x >= picos[N_ETIQUETAS - 1]) {
    idx[0] = N_ETIQUETAS - 1; grado[0] = 1.0; idx[1] = N_ETIQUETAS - 1; grado[1] = 0.0; return;
  }
  for (int k = 0; k < N_ETIQUETAS - 1; k++) {
    if (x >= picos[k] && x <= picos[k + 1]) {
      float rango = picos[k + 1] - picos[k];
      float gs = (rango > 0) ? (x - picos[k]) / rango : 0.0;
      idx[0] = k; grado[0] = 1.0 - gs; idx[1] = k + 1; grado[1] = gs;
      return;
    }
  }
  idx[0] = 3; grado[0] = 1.0; idx[1] = 3; grado[1] = 0.0;   // picos desordenados
}

float calcularDifusa(float error, float derivada) {
  int idxE[2], idxDE[2]; float gE[2], gDE[2];
  fuzzificar(error, E_PICOS, idxE, gE);
  fuzzificar(derivada, DE_PICOS, idxDE, gDE);
  float num = 0.0, den = 0.0;
  for (int a = 0; a < 2; a++) {
    if (gE[a] <= 0.0) continue;
    for (int b = 0; b < 2; b++) {
      if (gDE[b] <= 0.0) continue;
      float disparo = min(gE[a], gDE[b]);
      int is = constrain(idxE[a] + idxDE[b] - 3, 0, N_ETIQUETAS - 1);
      num += disparo * SALIDA_PICOS[is];
      den += disparo;
    }
  }
  return (den <= 0.0) ? 0.0 : num / den;
}

// ----------------------------------------------------------------------------
// MOTORES
// ----------------------------------------------------------------------------
void escribirMotor(int pinIn1, int pinIn2, int pinPwm, int velocidad) {
  if (velocidad >= 0) { digitalWrite(pinIn1, HIGH); digitalWrite(pinIn2, LOW); }
  else                { digitalWrite(pinIn1, LOW);  digitalWrite(pinIn2, HIGH); }
  ledcWrite(pinPwm, min(abs(velocidad), PWM_MAX));
}

void detenerMotores() {
  ledcWrite(PIN_PWMA, 0);
  ledcWrite(PIN_PWMB, 0);
}

void terminarCorrida(const char* motivo) {
  corriendo = false;
  detenerMotores();
  digitalWrite(PIN_STBY, LOW);
  motivoFin = motivo;
  Serial.print(">> FIN: "); Serial.println(motivo);
}

void guardarMuestra(float t, float vc, float err, float u) {
  buffer[totalMuestras % TAM_BUFFER] = { t, vc, err, u };
  totalMuestras++;
}

// ----------------------------------------------------------------------------
// PETICIONES DE LA APP
// ----------------------------------------------------------------------------
float argFloat(const char* nombre, float porDefecto) {
  return server.hasArg(nombre) ? server.arg(nombre).toFloat() : porDefecto;
}

// GET /iniciar?ctrl=...&parametros...
void pedirIniciar() {
  String c = server.arg("ctrl"); c.toLowerCase();
  Controlador nuevo = NINGUNO;
  if      (c == "pid")    { nuevo = PID_C;    nombreCtrl = "pid"; }
  else if (c == "difusa") { nuevo = DIFUSA_C; nombreCtrl = "difusa"; }
  else if (c == "lqr")    { nuevo = LQR_C;    nombreCtrl = "lqr"; }
  else if (c == "smc")    { nuevo = SMC_C;    nombreCtrl = "smc"; }
  if (nuevo == NINGUNO) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"controlador desconocido\"}");
    return;
  }

  velocidadBase = constrain((int)argFloat("base", velocidadBase), 0, PWM_MAX);

  if (nuevo == PID_C) {
    Kp = argFloat("kp", Kp); Ki = argFloat("ki", Ki); Kd = argFloat("kd", Kd);
  } else if (nuevo == DIFUSA_C) {
    char k[5];
    for (int i = 0; i < N_ETIQUETAS; i++) {
      snprintf(k, sizeof(k), "e%d",  i + 1); E_PICOS[i]      = argFloat(k, E_PICOS[i]);
      snprintf(k, sizeof(k), "de%d", i + 1); DE_PICOS[i]     = argFloat(k, DE_PICOS[i]);
      snprintf(k, sizeof(k), "s%d",  i + 1); SALIDA_PICOS[i] = argFloat(k, SALIDA_PICOS[i]);
    }
  } else if (nuevo == LQR_C) {
    K1 = argFloat("k1", K1); K2 = argFloat("k2", K2);
  } else {
    LAMBDA = argFloat("lambda", LAMBDA); K_SMC = argFloat("ksmc", K_SMC);
    PHI = max(argFloat("phi", PHI), 0.001f);
  }

  // Modelo y observador para la velocidad base de esta corrida
  float cmPorPwm = VEL_MAX_CM_S / PWM_MAX;
  vAvance = max(velocidadBase * cmPorPwm, 0.5f);
  gGiro   = 2.0 * cmPorPwm / ANCHO_EJES_CM;
  lObs1 = 2.0 * POLO_OBSERVADOR;
  lObs2 = POLO_OBSERVADOR * POLO_OBSERVADOR / vAvance;

  // Reiniciar estados
  controlador = nuevo;
  errorAnterior = 0.0; integral = 0.0; derivadaFiltrada = 0.0; primeraMuestra = true;
  lineaVisible = true; ultimaPosicionValida = 0.0;
  x1Est = posicionActual * SEP_SENSORES_CM; x2Est = 0.0; uAnterior = 0.0;
  totalMuestras = 0;
  motivoFin = "";
  inicioMs = millis();
  tiempoAnterior = inicioMs;
  ultimaPeticionMs = inicioMs;
  digitalWrite(PIN_STBY, HIGH);
  corriendo = true;

  Serial.print(">> INICIAR "); Serial.print(nombreCtrl);
  Serial.print("  base="); Serial.println(velocidadBase);
  server.send(200, "application/json", "{\"ok\":true}");
}

// GET /detener
void pedirDetener() {
  if (corriendo) terminarCorrida("manual");
  server.send(200, "application/json", "{\"ok\":true}");
}

// GET /datos?desde=N
void pedirDatos() {
  ultimaPeticionMs = millis();
  unsigned long desde = server.hasArg("desde") ? (unsigned long)server.arg("desde").toInt() : 0;
  if (totalMuestras > TAM_BUFFER && desde < totalMuestras - TAM_BUFFER) desde = totalMuestras - TAM_BUFFER;
  if (desde > totalMuestras) desde = totalMuestras;
  unsigned long hasta = totalMuestras;
  if (hasta - desde > 100) hasta = desde + 100;   // como mucho 100 por respuesta

  String json;
  json.reserve(160 + (hasta - desde) * 40);
  json = "{\"total\":" + String(totalMuestras);
  json += ",\"desde\":" + String(desde);
  json += ",\"corriendo\":" + String(corriendo ? "true" : "false");
  json += ",\"fin\":\"" + String(motivoFin) + "\"";
  json += ",\"ctrl\":\"" + String(nombreCtrl) + "\"";
  json += ",\"m\":[";
  for (unsigned long i = desde; i < hasta; i++) {
    const Muestra& m = buffer[i % TAM_BUFFER];
    if (i > desde) json += ",";
    json += "[" + String(m.t, 3) + ",0," + String(m.vc, 3) + "," + String(m.err, 3) + "," + String(m.u, 1) + "]";
  }
  json += "]}";
  server.send(200, "application/json", json);
}

// GET /  (solo para comprobar desde el navegador que el carrito responde)
void paginaEstado() {
  String txt = "Carrito seguidor de linea listo.\nUsa la app web del proyecto para controlarlo.\n";
  txt += "Estado: " + String(corriendo ? "CORRIENDO " : "DETENIDO ") + String(nombreCtrl) + "\n";
  txt += "Linea: " + String(lineaVisible ? "visible" : "perdida") + "  posicion = " + String(posicionActual, 2) + "\n";
  server.send(200, "text/plain; charset=utf-8", txt);
}

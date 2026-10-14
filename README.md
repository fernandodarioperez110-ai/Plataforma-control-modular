# Plataforma experimental modular para la comparación de estrategias de control

Aplicación web para configurar, ejecutar y comparar cuatro estrategias de control
(**PID, Lógica Difusa, LQR y SMC**) sobre dos prototipos físicos manejados por un
**ESP32-S3**:

- **Balancín (Ball and Beam):** sensor infrarrojo Sharp GP2Y0A21 + servomotor MG996R.
- **Carrito seguidor de línea:** arreglo de 5 sensores TCRT-5000 + driver TB6612FNG + 2 motorreductores DC.

Proyecto de investigación de Ingeniería en Mecatrónica, UNITEC.
Autor: Fernando Darío Pérez Munguía · Asesor: Ing. Favell Núñez.

## Pantallas de la aplicación

1. **Selección:** se elige el prototipo (Balancín o Carrito) y el controlador (PID, Lógica Difusa, LQR o SMC).
2. **Control:** se ingresan los parámetros del controlador y se observa en tiempo real la referencia, la variable controlada, el error y la señal de control.
3. **Datos:** tabla de las pruebas guardadas con Tiempo de ejecución, Error RMS, Sobreimpulso y Error estacionario, gráfica de respuesta de cada prueba, comparación entre pruebas y opción para eliminar registros.

## Arquitectura

```
Navegador (React)  ⇄  WebSocket / HTTP  ⇄  Backend (FastAPI)  ⇄  ESP32 Balancín (cable USB / serial)
                                              │               ⇄  ESP32 Carrito  (WiFi / HTTP)
                                              ├─ cálculo de métricas
                                              └─ SQLite (runs.db)
```

Cada prototipo tiene **un solo firmware** con los cuatro controladores. El controlador
y sus parámetros se envían desde la página al iniciar cada prueba, por lo que no es
necesario volver a cargar el código en el ESP32.

## Estructura del repositorio

```
backend/     Servidor FastAPI (Python): conexión con los ESP32, métricas y base de datos
frontend/    Interfaz web (React + Vite + Recharts)
firmware/
  BallAndBeam_Web_Cable/   Firmware del balancín (comunicación serial por USB)
  CarritoLinea_Web/        Firmware del carrito (red WiFi propia del ESP32, HTTP)
```

## Requisitos

- Python 3.10 o superior
- Node.js 18 o superior
- Arduino IDE con soporte para ESP32 (librería `ESP32Servo` para el balancín)

## Cómo correrlo

### 1. Backend (puerto 8000)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 2. Frontend

**Opción A, desarrollo (puerto 5173):**

```bash
cd frontend
npm install
npm run dev
```

Abrir http://localhost:5173 (Vite reenvía `/api` y `/ws` al backend en el puerto 8000).

**Opción B, producción (un solo servidor):**

```bash
cd frontend
npm install
npm run build
```

Con el backend corriendo, abrir http://localhost:8000.

## Configuración de los prototipos

En `backend/main.py`:

```python
USE_SIMULATOR = False      # True para probar sin hardware
SERIAL_PORT = "COM7"       # puerto USB del balancín

CONEXION = {
    "balancin": "serial",  # firmware/BallAndBeam_Web_Cable
    "carrito":  "http",    # firmware/CarritoLinea_Web
}
```

- **Balancín:** conectar el ESP32 por cable USB y ajustar `SERIAL_PORT`.
- **Carrito:** el ESP32 crea la red WiFi `ESP32-CARRITO` (contraseña `12345678`, IP `192.168.5.1`). Antes de iniciar una prueba, conectar la laptop a esa red.

### Protocolo serial (balancín)

```
PC    -> ESP32 :  START,<controlador>,<p1>,<p2>,...
PC    -> ESP32 :  STOP
ESP32 -> PC    :  DATA,<t>,<ref>,<vc>,<error>,<u>
ESP32 -> PC    :  DONE
```

### Endpoints HTTP (carrito)

```
GET /iniciar?ctrl=pid&base=180&kp=100&ki=0&kd=0.5
GET /datos?desde=N
GET /detener
```

El carrito guarda hasta 600 muestras en memoria para no perder datos si la
conexión WiFi se interrumpe brevemente.

## Condiciones de prueba usadas

| Prototipo | Referencia / condición | Duración | Periodo de muestreo |
|---|---|---|---|
| Balancín | Setpoint de 28 cm | 25 s | 30 ms |
| Carrito | Centrado sobre la línea, velocidad base 180 | 25 s | 20 ms |

## Métricas calculadas

- **Tiempo de ejecución:** duración total de la prueba.
- **Error RMS:** raíz del promedio de los errores al cuadrado.
- **Sobreimpulso:** porcentaje en que la salida supera la referencia (no aplica cuando la referencia es cero).
- **Error estacionario:** promedio del error en el último 15 % de la prueba.

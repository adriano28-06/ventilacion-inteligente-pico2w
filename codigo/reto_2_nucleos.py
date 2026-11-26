# ==========================================================
#  RETO DOS NUCLEOS - MEDICION "DESPUES" (control en nucleo 1, red en nucleo 0)
#  Nucleo 1: bucle de control (_thread). Nucleo 0: Wi-Fi + MQTT (asyncio)
# ==========================================================
from machine import Pin, ADC, PWM, SoftI2C
import network
import time
import asyncio
import _thread
import gc
from array import array
from umqtt.simple import MQTTClient
import secrets

MODO = "2 NUCLEOS (_thread + asyncio)"
DURACION_S = 180           # duracion de la prueba: 3 minutos
CONTROL_MS = 100           # el lazo de control deberia correr cada 100 ms
PERIODO_NUBE_MS = 3000     # publica cada 3 s (20 datos/min, dentro del limite)
RECONEXION_CADA_S = 30     # fuerza una reconexion Wi-Fi + MQTT cada 30 s
CO2_REF = 420
UMBRAL_ON = 1000
UMBRAL_OFF = 800

adc = ADC(Pin(26))
i2c = SoftI2C(sda=Pin(20), scl=Pin(21), freq=100000)
vent = PWM(Pin(16))
vent.freq(25000)
vent.duty_u16(0)
AHT = 0x38

N = DURACION_S * 1000 // CONTROL_MS
retrasos = array('H', [0] * N)   # retraso de cada vuelta del lazo, en ms
n_ret = 0
estado = {'co2': 0.0, 'pwm': 0, 'enc': False, 'cont': 0, 't': None, 'h': None}
rs_base = 1.0
wlan = None
cliente = None
candado = _thread.allocate_lock()
corriendo = True
terminado = False


def leer_mq():
    s = 0
    for i in range(8):
        s = s + adc.read_u16()
    return s / 8 * 3.3 / 65535 * 1.5


def aht_pedir():
    try:
        i2c.writeto(AHT, bytes([0xAC, 0x33, 0x00]))
    except OSError:
        pass


def aht_leer():
    try:
        d = i2c.readfrom(AHT, 6)
        estado['h'] = ((d[1] << 12) | (d[2] << 4) | (d[3] >> 4)) * 100 / 1048576
        estado['t'] = (((d[3] & 0x0F) << 16) | (d[4] << 8) | d[5]) * 200 / 1048576 - 50
    except OSError:
        pass


def paso_control(k):
    v = leer_mq()
    co2 = CO2_REF * ((5.0 / v - 1) / rs_base) ** -2.769
    if co2 >= UMBRAL_ON:
        estado['cont'] = estado['cont'] + 1
        if estado['cont'] >= 3:
            estado['enc'] = True
    else:
        estado['cont'] = 0
    if co2 <= UMBRAL_OFF:
        estado['enc'] = False
    if estado['enc']:
        p = 60 + (min(co2, 1500) - 1000) * 40 / 500
        if p < 60:
            p = 60
    else:
        p = 0
    vent.duty_u16(int(p * 65535 / 100))
    candado.acquire()
    estado['co2'] = co2
    candado.release()
    candado.acquire()
    estado['pwm'] = p
    candado.release()
    if k % 20 == 0:          # el AHT10 se lee cada 2 s, sin esperas bloqueantes
        aht_pedir()
    elif k % 20 == 1:
        aht_leer()


def registrar(r):
    global n_ret
    if r < 0:
        r = 0
    if r > 65535:
        r = 65535
    if n_ret < N:
        retrasos[n_ret] = r
        n_ret = n_ret + 1


def informe():
    datos = sorted(retrasos[:n_ret])
    n = len(datos)
    if n == 0:
        print("Sin datos")
        return
    mayores = 0
    for d in datos:
        if d > 100:
            mayores = mayores + 1
    print("")
    print("========== RESULTADO:", MODO, "==========")
    print("Muestras del lazo de control:", n)
    print("Retraso mediana  :", datos[n // 2], "ms")
    print("Retraso p95      :", datos[int(n * 0.95)], "ms")
    print("Retraso maximo   :", datos[-1], "ms")
    print("Vueltas con mas de 100 ms de retraso:", mayores)
    perdidas = 0
    for d in datos:
        if d > CONTROL_MS:
            perdidas = perdidas + d // CONTROL_MS
    print("Vueltas de control perdidas (aprox.):", perdidas)
    print("==================================================")


def conectar_wifi():
    w = network.WLAN(network.STA_IF)
    w.active(True)
    if not w.isconnected():
        w.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
        for i in range(20):
            if w.isconnected():
                break
            time.sleep(1)
    return w


def cerrar(c):
    # cierra el socket para no "perder" memoria de red (error ENOMEM)
    if c is None:
        return
    try:
        c.disconnect()
    except Exception:
        pass
    try:
        c.sock.close()
    except Exception:
        pass


def conectar_mqtt():
    gc.collect()
    c = MQTTClient("pico-reto", "io.adafruit.com",
                   user=secrets.AIO_USER, password=secrets.AIO_KEY, keepalive=60)
    try:
        c.connect()
    except Exception:
        cerrar(c)
        raise
    return c


def feed(nombre):
    return (secrets.AIO_USER + "/feeds/" + nombre).encode()


def nucleo1():
    # NUCLEO 1: solo el bucle de control, nunca toca la red
    global terminado
    prox = time.ticks_ms()
    k = 0
    while corriendo and k < N:
        registrar(time.ticks_diff(time.ticks_ms(), prox))
        paso_control(k)
        k = k + 1
        prox = time.ticks_add(prox, CONTROL_MS)
        espera = time.ticks_diff(prox, time.ticks_ms())
        if espera < 0:
            prox = time.ticks_ms()
            espera = 0
        time.sleep_ms(espera)
    terminado = True


async def nube():
    global cliente
    while True:
        try:
            if cliente is None:
                cliente = conectar_mqtt()
            candado.acquire()
            valor = int(estado['co2'])
            candado.release()
            cliente.publish(feed("co2"), str(valor))
        except Exception as e:
            print("nube:", e)
            cerrar(cliente)
            cliente = None
        await asyncio.sleep_ms(PERIODO_NUBE_MS)


async def reconexion():
    global cliente, wlan
    while True:
        await asyncio.sleep(RECONEXION_CADA_S)
        t0 = time.ticks_ms()
        cerrar(cliente)
        cliente = None
        wlan.disconnect()
        for i in range(30):              # espera a que se desconecte de verdad
            if not wlan.isconnected():
                break
            time.sleep_ms(100)
        wlan = conectar_wifi()
        time.sleep(1)                    # deja que el Wi-Fi obtenga su IP
        try:
            cliente = conectar_mqtt()
        except Exception:
            cliente = None
        print("Reconexion forzada:", time.ticks_diff(time.ticks_ms(), t0), "ms")


async def principal():
    t1 = asyncio.create_task(nube())
    t2 = asyncio.create_task(reconexion())
    while not terminado:
        await asyncio.sleep_ms(200)
    t1.cancel()
    t2.cancel()


print("Preparando:", MODO)
try:
    i2c.writeto(AHT, bytes([0xE1, 0x08, 0x00]))
except OSError:
    print("AHT10 no responde")
wlan = conectar_wifi()
print("Wi-Fi:", wlan.isconnected())
try:
    cliente = conectar_mqtt()
    print("MQTT: conectado")
except Exception as e:
    print("MQTT no conecto:", e)
time.sleep(5)
suma = 0
for i in range(10):
    suma = suma + leer_mq()
rs_base = 5.0 / (suma / 10) - 1
print("Midiendo durante", DURACION_S, "s... no toques nada")

_thread.start_new_thread(nucleo1, ())
try:
    asyncio.run(principal())
finally:
    corriendo = False
    for i in range(20):
        if terminado:
            break
        time.sleep_ms(100)
    vent.duty_u16(0)
    informe()

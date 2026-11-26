# ==========================================================
#  VENTILACION INTELIGENTE - programa completo con nube
#  Raspberry Pi Pico 2 W - MicroPython
#  Sensores: MQ-135 (GP26, ADC) y AHT10 (GP20/GP21, I2C)
#  Actuador: ventilador 12 V por MOSFET IRLZ44N (GP16, PWM 25 kHz)
#  Nube: MQTT a Adafruit IO (feeds co2, temperatura, humedad,
#        ventilador y alerta). Credenciales en secrets.py (en la Pico).
# ==========================================================
from machine import Pin, ADC, PWM, SoftI2C
import network
import time
from umqtt.simple import MQTTClient
import secrets

mq = ADC(26)
vent = PWM(Pin(16))
vent.freq(25000)            # 25 kHz: el ventilador no pita
vent.duty_u16(0)
i2c = SoftI2C(sda=Pin(20), scl=Pin(21))
AHT = 0x38                  # direccion I2C del AHT10


def leer_mq():
    # promedio de 8 lecturas; el divisor 10k/20k deja pasar 2/3 -> x1,5
    s = 0
    for i in range(8):
        s = s + mq.read_u16()
    v_adc = (s / 8) * 3.3 / 65535
    return v_adc * 1.5


def leer_aht():
    try:
        i2c.writeto(AHT, bytes([0xAC, 0x33, 0x00]))
        time.sleep_ms(80)
        d = i2c.readfrom(AHT, 6)
        h = ((d[1] << 12) | (d[2] << 4) | (d[3] >> 4)) * 100 / 1048576
        t = (((d[3] & 0x0F) << 16) | (d[4] << 8) | d[5]) * 200 / 1048576 - 50
        return t, h
    except OSError:
        return 0, 0


def conectar_wifi():
    w = network.WLAN(network.STA_IF)
    w.active(True)
    if not w.isconnected():
        w.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
        for i in range(20):
            if w.isconnected():
                break
            print("Conectando al Wi-Fi...")
            time.sleep(1)
    return w


def conectar_mqtt():
    c = MQTTClient("pico-ventilacion", "io.adafruit.com",
                   user=secrets.AIO_USER, password=secrets.AIO_KEY, keepalive=60)
    c.connect()
    return c


def feed(nombre):
    return (secrets.AIO_USER + "/feeds/" + nombre).encode()


try:
    i2c.writeto(AHT, bytes([0xE1, 0x08, 0x00]))   # inicializa el AHT10
except OSError:
    print("AHT10 no responde")

wlan = conectar_wifi()
print("Wi-Fi:", wlan.isconnected())
cliente = None
try:
    cliente = conectar_mqtt()
    print("MQTT: conectado a Adafruit IO")
except Exception as e:
    print("MQTT no conecto:", e)

print("Calentando el MQ-135 30 s, no acerques nada...")
for i in range(30, 0, -1):
    print("faltan", i, "s   V =", round(leer_mq(), 3))
    time.sleep(1)

# linea base: el aire actual se toma como 420 ppm
suma = 0
for i in range(10):
    suma = suma + leer_mq()
    time.sleep_ms(100)
rs_base = 5.0 / (suma / 10) - 1
print("Base lista -> 420 ppm")

encendido = False
altas = 0
alerta_anterior = -1
ultimo_envio = time.ticks_ms() - 15000

try:
    while True:
        # 1) MEDIR: CO2 estimado (no es medicion selectiva)
        v = leer_mq()
        if v < 0.05:
            v = 0.05
        rs = 5.0 / v - 1
        if rs < 0.01:
            rs = 0.01
        co2 = 420 * (rs / rs_base) ** -2.769

        # 2) DECIDIR: histeresis, ON tras 3 lecturas >= 1000, OFF en <= 800
        if co2 >= 1000:
            altas = altas + 1
        else:
            altas = 0
        if altas >= 3:
            encendido = True
        if co2 <= 800:
            encendido = False

        # 3) ACTUAR: PWM de 60 % (1000 ppm) a 100 % (1500 ppm)
        if encendido:
            p = 60 + (min(co2, 1500) - 1000) * 40 / 500
            if p < 60:
                p = 60
        else:
            p = 0
        vent.duty_u16(int(p * 65535 / 100))

        t, h = leer_aht()
        if co2 >= 1000:
            alerta = 1
        else:
            alerta = 0
        print("CO2 ~", int(co2), "ppm | vent", int(p), "% | T", round(t, 1), "C | H", round(h), "% | alerta", alerta)

        # 4) AVISAR: alerta al cambiar; telemetria cada 15 s (limite 30 datos/min)
        try:
            if cliente is None:
                if not wlan.isconnected():
                    wlan = conectar_wifi()
                cliente = conectar_mqtt()
                print("MQTT reconectado")
            if alerta != alerta_anterior:
                cliente.publish(feed("alerta"), str(alerta))
                alerta_anterior = alerta
            if time.ticks_diff(time.ticks_ms(), ultimo_envio) >= 15000:
                cliente.publish(feed("co2"), str(int(co2)))
                cliente.publish(feed("ventilador"), str(int(p)))
                cliente.publish(feed("temperatura"), str(round(t, 1)))
                cliente.publish(feed("humedad"), str(round(h, 1)))
                ultimo_envio = time.ticks_ms()
                print("   -> enviado a Adafruit IO")
        except Exception as e:
            print("Nube:", e)
            try:
                cliente.sock.close()
            except Exception:
                pass
            cliente = None

        time.sleep(1)
finally:
    vent.duty_u16(0)          # al presionar STOP el ventilador se apaga
    print("Ventilador apagado")

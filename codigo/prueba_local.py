# ==========================================================
#  PRUEBA LOCAL (sin nube): sensores + histeresis + ventilador
#  Raspberry Pi Pico 2 W - MicroPython
#  MQ-135 en GP26 (ADC, con divisor 10k/20k), AHT10 en GP20/GP21 (I2C),
#  ventilador 12 V por MOSFET IRLZ44N en GP16 (PWM a 25 kHz)
# ==========================================================
from machine import Pin, ADC, PWM, SoftI2C
import time

mq = ADC(26)
vent = PWM(Pin(16))
vent.freq(25000)          # 25 kHz: el ventilador no pita
vent.duty_u16(0)          # arranca apagado
i2c = SoftI2C(sda=Pin(20), scl=Pin(21))
AHT = 0x38                # direccion I2C del AHT10


def leer_mq():
    # promedia 8 lecturas y recupera el voltaje real del sensor
    s = 0
    for i in range(8):
        s = s + mq.read_u16()
    v_adc = (s / 8) * 3.3 / 65535
    return v_adc * 1.5    # el divisor deja pasar 2/3 -> se multiplica por 1,5


def leer_aht():
    # pide una medicion, espera 80 ms y convierte los 6 bytes
    try:
        i2c.writeto(AHT, bytes([0xAC, 0x33, 0x00]))
        time.sleep_ms(80)
        d = i2c.readfrom(AHT, 6)
        h = ((d[1] << 12) | (d[2] << 4) | (d[3] >> 4)) * 100 / 1048576
        t = (((d[3] & 0x0F) << 16) | (d[4] << 8) | d[5]) * 200 / 1048576 - 50
        return t, h
    except OSError:
        return 0, 0


try:
    i2c.writeto(AHT, bytes([0xE1, 0x08, 0x00]))   # inicializa el AHT10
except OSError:
    print("AHT10 no responde")

print("Calentando el MQ-135 30 s, no acerques nada...")
for i in range(30, 0, -1):
    print("faltan", i, "s   V =", round(leer_mq(), 3))
    time.sleep(1)

# linea base: el aire actual se toma como 420 ppm
suma = 0
for i in range(10):
    suma = suma + leer_mq()
    time.sleep_ms(100)
v_base = suma / 10
rs_base = 5.0 / v_base - 1
print("Base lista. V base =", round(v_base, 3), " -> 420 ppm")

encendido = False
altas = 0
try:
    while True:
        v = leer_mq()
        if v < 0.05:
            v = 0.05
        rs = 5.0 / v - 1                      # proporcional a la resistencia del sensor
        if rs < 0.01:
            rs = 0.01
        co2 = 420 * (rs / rs_base) ** -2.769  # CO2 ESTIMADO (no es medicion selectiva)

        # histeresis: enciende tras 3 lecturas >= 1000, apaga en <= 800
        if co2 >= 1000:
            altas = altas + 1
        else:
            altas = 0
        if altas >= 3:
            encendido = True
        if co2 <= 800:
            encendido = False

        # PWM proporcional: 60 % en 1000 ppm hasta 100 % en 1500 ppm
        if encendido:
            p = 60 + (min(co2, 1500) - 1000) * 40 / 500
            if p < 60:
                p = 60
        else:
            p = 0
        vent.duty_u16(int(p * 65535 / 100))

        t, h = leer_aht()
        print("V =", round(v, 3), "| CO2 ~", int(co2), "ppm | vent", int(p), "% | T", round(t, 1), "C | H", round(h), "%")
        time.sleep(1)
finally:
    vent.duty_u16(0)      # al presionar STOP el ventilador se apaga
    print("Ventilador apagado")

from io import BytesIO
import aioble
from bluetooth import UUID
import asyncio
import struct
import binascii

PHYPHOX_EXPERIMENT = "phyphox-Experiment.phyphox"

_PHYPHOX_SERVICE_UUID = UUID("cddf0001-30f7-4671-8b43-5e40ba53514a")
_PHYPHOX_EXPERIMENT_CHAR_UUID = UUID("cddf0002-30f7-4671-8b43-5e40ba53514a")
_PHYPHOX_EXPERIMENT_CONTROL_CHAR_UUID = UUID("cddf0003-30f7-4671-8b43-5e40ba53514a")

_PHYPHOX_DATA_SERVICE_UUID = UUID("cddf1001-30f7-4671-8b43-5e40ba53514a")
_PHYPHOX_CONFIG_CHAR = UUID("cddf1003-30f7-4671-8b43-5e40ba53514a")
_PHYPHOX_DATA_CHAR = UUID("cddf1002-30f7-4671-8b43-5e40ba53514a")

_ADV_INTERVAL_MS = 250_000

'''https://www.engeniustech.com/technical-papers/bluetooth-low-energy.pdf'''
_MTU_SIZE = const(247)


phyphox_service = aioble.Service(_PHYPHOX_SERVICE_UUID)
phyphox_service_exp_char = aioble.Characteristic(phyphox_service, _PHYPHOX_EXPERIMENT_CHAR_UUID, read=True, notify=True)
phphox_service_exp_control_char = aioble.Characteristic(phyphox_service, _PHYPHOX_EXPERIMENT_CONTROL_CHAR_UUID, write=True)

phyphox_data_service = aioble.Service(_PHYPHOX_DATA_SERVICE_UUID)
phyphox_data_service_config_char = aioble.Characteristic(phyphox_data_service, _PHYPHOX_CONFIG_CHAR, read=True, write=True, notify=False)
phyphox_data_service_data_char = aioble.Characteristic(phyphox_data_service, _PHYPHOX_DATA_CHAR, read=True, write=True, notify=True)

aioble.register_services(phyphox_service, phyphox_data_service)


def CRC32_from_file(filename):
    buf = open(filename,'rb').read()
    buf = (binascii.crc32(buf) & 0xFFFFFFFF)
    return int("%08X" % buf, 16)

async def transfer_experiment():
    with open(PHYPHOX_EXPERIMENT, "r") as experiment_file:
        data = experiment_file.read().encode("utf-8")
        experiment = BytesIO(data)
        exp_len = experiment.seek(0,2)
        checksum = CRC32_from_file(PHYPHOX_EXPERIMENT)
        header = "phyphox".encode() + struct.pack('>I',exp_len) + struct.pack('>I',checksum) + b'\x00' + b'\x00' + b'\x00' + b'\x00' + b'\x00'
        #see discussion below
        while True:
            await phphox_service_exp_control_char.written(timeout_ms=None)
            phyphox_service_exp_char.write(header, send_update=True)
            DELAY = 0.03
            asyncio.sleep(DELAY)
            N = _MTU_SIZE - 3
            #TODO: how does this value depends on _MTU_SIZE? Is it rellay -3? Not sure.. https://punchthrough.com/ble-throughput-part-4/ 
            for i in range(int(exp_len/N)):
                experiment.seek(i*N)
                byteSlice = experiment.read(N)
                phyphox_service_exp_char.write(byteSlice, send_update=True)
                asyncio.sleep(DELAY)
            if(exp_len%N != 0):
                rest = exp_len%N
                experiment.seek(exp_len - rest)
                byteSlice = experiment.read(rest)
                phyphox_service_exp_char.write(byteSlice, send_update=True)


async def send_random_float32(event):
    import random
    while True:
        #Only send data if a central is connected stop otherwise
        await event.wait()
        value = random.uniform(1.8,5.0)
        print(f"Sending value: {value}")
        phyphox_data_service_data_char.write(struct.pack("<f", value), send_update=True)
        await asyncio.sleep(0.5)


async def advertising(event):
    while True:
        async with await aioble.advertise(_ADV_INTERVAL_MS, name="phyphox_box", services=[_PHYPHOX_SERVICE_UUID]) as connection:
            print("Connected")
            event.set()
            await connection.exchange_mtu(_MTU_SIZE)
            await connection.disconnected(timeout_ms=None)
            print("Disconnected")
            event.clear()


async def main():
    event_connected = asyncio.Event()
    task_sensor = asyncio.create_task(send_random_float32(event_connected))
    task_experiment = asyncio.create_task(transfer_experiment())
    task_advertising = asyncio.create_task(advertising(event_connected))
    #Note: TaskGroup would be better suited but it is not yet supported in mpy (Dec24)
    await asyncio.gather(task_advertising, task_experiment, task_sensor)

if __name__ == "__main__":
        asyncio.run(main())


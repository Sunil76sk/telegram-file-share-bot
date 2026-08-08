import os
os.environ["UPI_ID"] = ""
os.environ["UPI_QR_IMAGE"] = ""
os.environ["SAAS_UPI_ID"] = ""

import sys
sys.path.insert(0, os.getcwd())

import config
print(f"config.UPI_ID = {repr(config.UPI_ID)}")
print(f"config.UPI_QR_IMAGE = {repr(config.UPI_QR_IMAGE)}")
print(f"config.SAAS_UPI_ID = {repr(config.SAAS_UPI_ID)}")

assert config.UPI_ID == "sunil.kembhavi@ybl"
assert config.UPI_QR_IMAGE == "assets/upi_qr.png"
assert config.SAAS_UPI_ID == "sunil.kembhavi@ybl"
print("SUCCESS: Fallback logic works correctly!")

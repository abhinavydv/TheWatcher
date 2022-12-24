from socket import getaddrinfo, AF_INET, AF_INET6
from Base.constants import ImageSendModes


ADDRESS_TYPE = AF_INET
if ADDRESS_TYPE == AF_INET6:
    SERVER_ADDRESS = getaddrinfo("watcher.centralindia.cloudapp.azure.com", None)[0][4][0]
elif ADDRESS_TYPE == AF_INET:
    SERVER_ADDRESS = "192.168.212.223"
else:
    raise Exception(f"Undefined Address type '{ADDRESS_TYPE}'")
SERVER_PORT = 11419
WEB_SERVER_ADDRESS = SERVER_ADDRESS
WEB_SERVER_PORT = 8080
ACKNOWLEDGEMENT_ITERATION = 10
IMAGE_SEND_MODE = ImageSendModes.DIRECT_JPG

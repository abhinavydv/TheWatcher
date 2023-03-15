from socket import getaddrinfo, AF_INET, AF_INET6
from Base.constants import ImageSendModes


ADDRESS_TYPE = AF_INET
# if ADDRESS_TYPE == AF_INET6:
#     SERVER_ADDRESS = getaddrinfo("watcher.centralindia.cloudapp.azure.com",
#                                  None)[0][4][0]
# elif ADDRESS_TYPE == AF_INET:
#     SERVER_ADDRESS = getaddrinfo("watcher.centralindia.cloudapp.azure.com",
#                                  None)[3][4][0]
#     # SERVER_ADDRESS = "localhost"
# else:
#     raise ValueError(f"Unknown Address type '{ADDRESS_TYPE}'")

addresses = getaddrinfo("watcher.centralindia.cloudapp.azure.com",
                                 None)

for addr in addresses:
    # print(addr)
    if addr[0] == ADDRESS_TYPE:
        SERVER_ADDRESS = addr[4][0]

SERVER_PORT = 5432
WEB_SERVER_ADDRESS = SERVER_ADDRESS
WEB_SERVER_PORT = 8080
ACKNOWLEDGEMENT_ITERATION = 10
IMAGE_SEND_MODE = ImageSendModes.DIRECT_JPG
CONTROLLER_HEADER_SIZE = 8

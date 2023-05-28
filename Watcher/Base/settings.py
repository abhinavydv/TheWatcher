from socket import getaddrinfo, AF_INET, AF_INET6
from Base.constants import ImageSendModes


ADDRESS_TYPE = AF_INET  # type of address to use (ipv4 or ipv6)
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
        SERVER_ADDRESS = addr[4][0] # address of the server

SERVER_PORT = 11419      # port of the server running
WEB_SERVER_ADDRESS = SERVER_ADDRESS # address of the file server
WEB_SERVER_PORT = 8080  # port of the file server

# After sending data this many times, requests for an acknowledgment (OK)
ACKNOWLEDGEMENT_ITERATION = 10
IMAGE_SEND_MODE = ImageSendModes.DIRECT_JPG
CONTROLLER_HEADER_SIZE = 8  # size of the header used by controller client

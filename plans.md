## Plans for further development

### Obfuscation
1. gibberish code
    - Use pyminifier to remove docs and change variable names
2. Compile options
    - cython
    - nuitka
3. Other
    - pyarmor
4. Idea
    - Make scripts gibberish using pyminifier
    - Arm them using pyarmor
    - compile using nuitka

### Screenshots
1. tty
    - fbcat
    - fbgrab
2. screen
    - pipewire

### Execute a code on target machine
1. use reverse ssh tunneling
2. use ptyprocess (pypi)


### send this target code on victim
1. create a binary with .docs (fools to think that it's a doc file, it's not a correct extension) that gets executed on double click in stead of opening in the associated app. Also add a thumbnail image for the binary if possible.



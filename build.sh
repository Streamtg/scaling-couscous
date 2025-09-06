# descarga el binario
wget https://github.com/openziti/zrok/releases/download/v1.1.3/zrok_1.1.3_linux_amd64.tar.gz
tar -xzf zrok_1.1.3_linux_amd64.tar.gz   # extrae solo el ejecutable 'zrok'
rm zrok_1.1.3_linux_amd64.tar.gz CHANGELOG.md LICENSE README.md
chmod +x zrok
./zrok enable 63wdti52mg49

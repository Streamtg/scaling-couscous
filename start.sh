# 1) lanza zrok en bg (desde el repo)
zrok enable 63wdti52mg49
# copia el token que aparece (empieza por ghp_… o similar)
./zrok access private 63wdti52mg49 --bind 127.0.0.1:8080 &
sleep 5
# 2) arranca el proxy
exec npm start

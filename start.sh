# 1) lanza zrok en bg (desde el repo)
./zrok access private 63wdti52mg49 --bind 127.0.0.1:8080 &
sleep 5
# 2) arranca el proxy
exec npm start

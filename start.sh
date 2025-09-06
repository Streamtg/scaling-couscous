#!/usr/bin/env bash
# lanza zrok access en bg y luego node
zrok access private 63wdti52mg49 --bind 127.0.0.1:8080 &
sleep 5        # da tiempo a que el socket esté listo
npm start

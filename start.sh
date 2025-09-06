#!/usr/bin/env bash
# lanza zrok access en bg y luego node
zrok access private wvszln4dyz9q --bind 127.0.0.1:9191 &
sleep 5        # da tiempo a que el socket esté listo
npm start

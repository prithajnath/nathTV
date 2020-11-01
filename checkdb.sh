#!/usr/bin/env bash
for i in {1..5}
do
    psql -h cctv-postgres -U postgres --db postgres -c "\\d"
    [ $? -eq 0 ] && exit
    sleep 5
done
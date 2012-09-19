#!/bin/bash
while read p; do
  echo $p; /usr/bin/time ./$1 $p >res/$p 2>err/$p &
done <$2
wait


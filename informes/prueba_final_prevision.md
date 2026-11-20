# Prueba final de la previsión de fallos

La cuenta por modelo y edad no gana a repetir los fallos del trimestre anterior en el año guardado. Se equivoca en 0,3176 fallos por cada fallo real, frente a 0,3058 de la referencia. Se sigue usando la referencia, como fija la regla de la previsión.

## Lo que lo sostiene

El año guardado va de 2025T3 a 2026T2. En esos trimestres hubo 4.751 fallos de discos de datos. La cuenta previó 5.340,6.
Repetir el trimestre anterior daba 4.290. Frente a los fallos reales, la cuenta prevé un 12,4 % más y la referencia prevé un 9,7 % menos.

El error de un trimestre es la suma de lo que se equivoca la previsión en cada capacidad, sin signo, entre sus fallos reales.

| Trimestre | Fallos reales | Previstos por la cuenta | Referencia | Error de la cuenta | Error de la referencia |
|---|---:|---:|---:|---:|---:|
| 2025T3 | 1.254 | 1.370,0 | 1.061 | 0,3386 | 0,2432 |
| 2025T4 | 945 | 1.444,1 | 1.254 | 0,5977 | 0,4772 |
| 2026T1 | 1.030 | 1.228,9 | 945 | 0,2448 | 0,1990 |
| 2026T2 | 1.522 | 1.297,5 | 1.030 | 0,1757 | 0,3233 |

## Cada trimestre y capacidad

Entran las capacidades con discos el primer día del trimestre, con fallos en él o con fallos en el trimestre anterior.

| Trimestre | Capacidad (TB) | Previstos | Reales | Referencia |
|---|---:|---:|---:|---:|
| 2025T3 | 4 | 0,1 | 0 | 1 |
| 2025T3 | 8 | 155,8 | 86 | 115 |
| 2025T3 | 10 | 13,5 | 20 | 12 |
| 2025T3 | 12 | 457,7 | 362 | 388 |
| 2025T3 | 14 | 294,0 | 210 | 174 |
| 2025T3 | 16 | 325,8 | 459 | 277 |
| 2025T3 | 18 | 0,3 | 0 | 0 |
| 2025T3 | 20 | 26,0 | 21 | 20 |
| 2025T3 | 22 | 65,4 | 50 | 46 |
| 2025T3 | 24 | 31,4 | 46 | 28 |
| 2025T4 | 4 | 0,1 | 1 | 0 |
| 2025T4 | 8 | 111,3 | 122 | 86 |
| 2025T4 | 10 | 5,2 | 13 | 20 |
| 2025T4 | 12 | 403,2 | 318 | 362 |
| 2025T4 | 14 | 325,5 | 143 | 210 |
| 2025T4 | 16 | 427,4 | 222 | 459 |
| 2025T4 | 18 | 0,4 | 0 | 0 |
| 2025T4 | 20 | 51,4 | 28 | 21 |
| 2025T4 | 22 | 60,1 | 25 | 50 |
| 2025T4 | 24 | 59,5 | 72 | 46 |
| 2025T4 | 26 | 0,0 | 1 | 0 |
| 2026T1 | 4 | 0,1 | 0 | 1 |
| 2026T1 | 8 | 98,6 | 65 | 122 |
| 2026T1 | 10 | 16,6 | 11 | 13 |
| 2026T1 | 12 | 353,6 | 363 | 318 |
| 2026T1 | 14 | 270,3 | 143 | 143 |
| 2026T1 | 16 | 337,7 | 283 | 222 |
| 2026T1 | 18 | 0,3 | 0 | 0 |
| 2026T1 | 20 | 41,4 | 42 | 28 |
| 2026T1 | 22 | 45,8 | 42 | 25 |
| 2026T1 | 24 | 62,9 | 77 | 72 |
| 2026T1 | 26 | 1,6 | 4 | 1 |
| 2026T2 | 8 | 95,2 | 152 | 65 |
| 2026T2 | 10 | 14,4 | 23 | 11 |
| 2026T2 | 12 | 360,1 | 497 | 363 |
| 2026T2 | 14 | 257,0 | 273 | 143 |
| 2026T2 | 16 | 360,3 | 343 | 283 |
| 2026T2 | 18 | 0,3 | 0 | 0 |
| 2026T2 | 20 | 55,1 | 64 | 42 |
| 2026T2 | 22 | 49,7 | 63 | 42 |
| 2026T2 | 24 | 98,8 | 95 | 77 |
| 2026T2 | 26 | 6,5 | 12 | 4 |

## Límites

- El error se da sin intervalo, como en el análisis: es una sola medida de todos los trimestres juntos.
- La referencia del primer trimestre son los fallos reales de 2025T2 del análisis.
- Quedan sin repartir 120.643 días de disco de celdas de modelo, centro y mes sin ninguna foto. No cuentan en las tasas de los trimestres siguientes.
- El año guardado se midió una sola vez, después del ensayo con la validación.

## Lo que se puede hacer ya

- Llevar el resultado al informe final, al cuadro de mando y al README.

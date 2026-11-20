# Prueba final del modelo de riesgo

El modelo se da por bueno en el año guardado: en la lista de los 100 discos de más riesgo de cada mes encuentra de media 7,73 fallos más que la regla de los cinco avisos SMART. El intervalo de esa diferencia va de 4,82 a 11,45, por encima de cero.

El listón era encontrar más fallos que la regla en la lista de 100, con el intervalo por encima de cero y un AUC de 0,70 o más. Con todas las fotos medidas juntas, el AUC del modelo es 0,873. El de la regla es 0,816.

## Lo que lo sostiene

Se midieron los meses de julio de 2025 a mayo de 2026, con 3.643.207 fotos de discos de datos. De ellas, 3.773 tuvieron un fallo en los 30 días siguientes a la foto.

Cada mes, el modelo encontró de media 22,64 fallos en su lista y la regla, 14,91. Los dos se midieron en las mismas fotos. El intervalo sale de remuestrear los meses mil veces.

| Mes | Fotos medidas | Fallos | Modelo, lista de 100 | Regla, lista de 100 | Modelo, lista de 20 | Regla, lista de 20 |
|---|---:|---:|---:|---:|---:|---:|
| julio de 2025 | 317.799 | 350 | 27 | 5 | 8 | 1 |
| agosto de 2025 | 318.326 | 384 | 22 | 18 | 5 | 2 |
| septiembre de 2025 | 320.652 | 395 | 29 | 19 | 8 | 3 |
| octubre de 2025 | 326.882 | 404 | 25 | 13 | 8 | 3 |
| noviembre de 2025 | 332.804 | 300 | 16 | 14 | 6 | 3 |
| diciembre de 2025 | 333.027 | 124 | 15 | 7 | 5 | 2 |
| enero de 2026 | 334.790 | 264 | 18 | 14 | 7 | 4 |
| febrero de 2026 | 333.693 | 290 | 20 | 19 | 8 | 6 |
| marzo de 2026 | 336.818 | 327 | 19 | 13 | 7 | 5 |
| abril de 2026 | 341.809 | 505 | 28 | 20 | 9 | 6 |
| mayo de 2026 | 346.607 | 430 | 30 | 22 | 10 | 8 |

## Las medidas de al lado

No deciden si el modelo se da por bueno. Son los fallos de todos los meses medidos, sumados. La última columna cuenta las marcas que da la puntuación de cada mes, que deshace los empates por número de serie.

| Lista | Modelo | Regla | Marcas del modelo |
|---:|---:|---:|---:|
| 20 | 81 | 43 | 81 |
| 100 | 249 | 164 | 249 |
| 500 | 741 | 403 | 741 |
| 1000 | 1.157 | 477 | 1.157 |

Con todos los meses juntos, la correlación de Matthews de la lista de 100 es 0,122 para el modelo. Para la regla es 0,080.

## Tomos donde acaba de fallar un disco

Un tomo está en peligro mientras se reconstruye un disco de datos suyo que falló: un día por TB, más uno de espera. En los meses medidos hubo 40.628 fotos en tomos en peligro. De ellas, 113 tuvieron un fallo en sus 30 días.

Cada mes se miró el 5 % de esas fotos con más riesgo, 2.030 fotos en total. Entre ellas, el modelo encontró 63 fallos y la regla, 55.

## Lo que no se midió

- Disco de arranque: fuera del modelo. Son 43.512 fotos sin puntuar.
- Foto del día del fallo: el disco ya está marcado como fallado. Son 123 fotos sin puntuar.
- La foto de junio de 2026: su horizonte de 30 días acaba después del 30/06/2026, fuera del año guardado.

## Datos personales

No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección porque son de discos y no de personas (reglas, apartado 9). serial_number identifica un disco; esta prueba no usa ni deja ninguna columna de datos personales.

## Límites

- La medida de los tomos se apoya en 113 fallos en tomos en peligro, pocos para decidir con ellos.
- Se quedan fuera de los tomos 132 fallos de discos de datos cuya ventana no trae centro, vault y ranura.
- Para la correlación de Matthews, la lista de la regla deshace los empates por número de serie, igual que la del modelo.
- Las listas de cada mes reparten en proporción un empate en el último puesto, como en el modelado. Las marcas de la puntuación de cada mes lo deshacen por número de serie.
- El modelo examinado aquí no se volvió a elegir ni a ajustar con nada del año guardado. El que se usa hoy, reentrenado con un año más de datos, se midió en este año antes de aprobarlo: para él no es una prueba independiente.

## Lo que se puede hacer ya

- Medir el reentreno con el año guardado: `produccion/reentrenar.py` con `--medir` sobre la tabla de este año. El reentreno no sustituye al modelo en uso: eso lo decide el responsable del caso.

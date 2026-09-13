# Suite de Diseño Digital RTL & FSM (ELO212 / IPD432 - USM)

Aplicación desarrollada en Python y PySide6 concebida para cumplir rigurosamente las convenciones de diagramas y especificación formal de los cursos:
- **ELO212:** Convenciones para esquemáticos y diagramas de alto nivel.
- **IPD432:** Guidelines for Finite State Machines (FSMs) and SystemVerilog implementation.

---

## 🚀 Cómo Ejecutar la Aplicación

Asegúrate de contar con Python 3.10+ y `PySide6`:

```bash
python -m pip install PySide6
python main.py
```

Para correr las pruebas automáticas del sistema:
```bash
python -m unittest discover -s tests
```

---

## 🛠️ Características Principales

### 1. 📐 Editor Esquemático RTL (Reglas ELO212)
* **Trazado Ortogonal Estricto (Manhattan Routing):** Prohíbe diagonales o curvas, trazando automáticamente esquinas en ángulo recto entre pines.
* **Biblioteca de Primitivas Estandarizadas:**
  * **Multiplexor (MUX):** Trapecio canónico con entradas por la cara ancha izquierda, salida por la derecha y selección en la base inferior.
  * **Registros / Flip-Flops:** Caja con entradas `D`, salida `Q`, símbolo triangular de reloj (`^`), pin `rst` y soporte de ancho (`/N`).
  * **Operadores Circulares:** Primitivas aritméticas como `+`, `A>B`, `*`.
  * **Compuertas Lógicas:** AND, OR, NOT (con burbuja), XOR.
  * **Desagregador de Bus (Bus Splitter):** Barra perpendicular al bus original con ramales y etiquetas de subgrupos (`[2:0]`, `[3]`, `[15:4]`).
  * **Constantes:** Generadores explícitos de valores constantes (`1'b0`, `4'd1`, `8'hFF`) para evitar entradas flotantes.
* **Puntos de Conexión (*Solder Dots*):** Marcado explícito de cruces conectados vs no conectados.
* **Anotación de Buses:** Diagonal con ancho de bits (`/N`) o identificadores indexados (`bus[N:0]`).

### 2. 🔄 Diseñador y Validador de FSM (Reglas IPD432)
* **Definición Tabular / Opciones:**
  * Define puertos de I/O con valores por defecto anti-latch.
  * Configura estados con nombres simbólicos y salidas Moore.
  * Define transiciones con condiciones (`TA == 1'b0`, `else`), temporizadores (`t = T - 1`) y salidas Mealy.
* **Plantillas Canónicas del Curso:**
  * **Semáforo (4 Estados - Moore):** Controlador de intersección de vías con sensores `TA`/`TB` y luces `LA`/`LB`.
  * **Conversor Nivel a Pulso (3 Estados - Moore):** Detector de pulso canónico del curso (slides 35-54).
  * **Detector de Secuencia '101' (3 Estados - Mealy):** Máquina de Mealy con salidas en las transiciones (`din == 1'b1 / pattern_found=1'b1`), ilustrando el ahorro de estados y la respuesta inmediata característica de Mealy.
* **Motor de Validación Formal:**
  * Previene la inferencia accidental de *latches*.
  * Comprueba transiciones estrictamente complementarias y deterministas.
  * Detecta estados muertos (*deadlocks*) o estados inalcanzables.
* **Auto-Render del Diagrama de Estados:**
  * **Moore:** Círculos divididos con línea horizontal (arriba: nombre del estado; abajo: valores de las salidas).
  * **Mealy:** Círculo simple con salidas marcadas sobre las flechas de transición (`condición / salidas`).
  * Flecha direccional de **Reset** apuntando al estado inicial.
  * Estados completamente arrastrables para acomodar el diagrama con comodidad.
* **Generador Canónico SystemVerilog:**
  * Plantilla canónica de **2 bloques `always`** (`always_ff` y `always_comb` con asignación inicial anti-latch).
  * Opción de **3 bloques `always`** con salidas registradas opcionales (*glitch-free*).
  * Codificación mediante `typedef enum logic [k-1:0] state_t` y atributos de síntesis Vivado opcionales (`one_hot`, `sequential`, etc.).

### 3. 📤 Exportación para Informes Académicos
* **Exportación SVG Vectorial:** Ideal para incrustar directamente en LaTeX sin pixelación a cualquier nivel de zoom.
* **Exportación PNG de Alta Resolución:** Imágenes nítidas con fondo blanco limpio.
* **Exportación de Código SystemVerilog:** Archivos `.sv` listos para simular en ModelSim/Questa o sintetizar en Vivado.
* **Guardado y Carga de Proyectos:** Archivos `.json` que guardan tanto el esquemático RTL como la FSM.

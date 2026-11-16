# MV Crypto Intelligence — backtesting

Ejecuta **Actions → MV Crypto Backtesting → Run workflow**. Descarga el artifact **mv-crypto-results** al finalizar.

Prueba BTCUSDT, ETHUSDT y SOLUSDT en 15m, 1h, 4h y 1d; cuatro estrategias, 70% entrenamiento / 30% prueba. Datos públicos de Binance Spot (2024). Costos simulados: comisión 0.1% por lado y deslizamiento 0.05% por ejecución. Operaciones long-only, sin apalancamiento, con stops 2 ATR y objetivos 3 ATR. Capital inicial simulado 10,000 USD, riesgo estimado 1% por operación.

**Advertencia:** backtests hipotéticos; no son evidencia de rentabilidad futura. Revisar integridad de datos, sesgos y consistencia fuera de muestra antes de usar señales. No se ejecutan órdenes ni se necesitan claves API.

El CSV y status.json se generan en results/. Si falta un archivo mensual, la ejecución falla y status.json registra los faltantes.

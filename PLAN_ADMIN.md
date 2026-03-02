# Plan: Implementación de Acceso al Panel de Admin Binance

## Información Recopilada:

- **URL actual de órdenes P2P**: `https://p2p.binance.com/es/fiatOrder`
- **Nueva URL del panel de admin**: `https://c2c-admin.binance.com/es/order/pending`
- **Botón a hacer clic**: `<img id="c2c-m-pendingOrders_btn_switchView" src="..." alt="table">`
- **Función de referencia**: `marcar_ordenes_pagadas()` - usa Selenium para hacer clic en pestañas y extraer IDs

## Plan de Implementación:

### 1. Agregar nueva configuración (líneas ~70)
- Agregar `URL_ORDENES_ADMIN = "https://c2c-admin.binance.com/es/order/pending"`
- Agregar variable de modo: `self.modo_admin = False`

### 2. Crear función `acceder_panel_admin()` 
- Navegar a la URL del panel de admin
- Esperar a que cargue la página
- Hacer clic en el botón de vista de tabla usando el ID `c2c-m-pendingOrders_btn_switchView`
- Loguear éxito/fallo

### 3. Crear función `procesar_ordenes_admin()`
- Extraer IDs de órdenes del panel de admin (similar a `marcar_ordenes_pagadas`)
- Marcar órdenes como procesadas en memoria

### 4. Modificar `proceso_carga_backend()` 
- Agregar opción para elegir modo P2P normal o Admin
- Si es modo Admin: llamar a `acceder_panel_admin()` antes de iniciar el escaneo

### 5. Modificar `bucle_principal()`
- Agregar detección de URL del panel admin (`c2c-admin.binance.com`)
- Procesar órdenes desde el panel de admin

## Archivos a editar:
- `Binance_Monitor_V28_Final.py` (único archivo)

## Pasos de prueba:
1. Ejecutar el programa
2. Verificar que puede acceder al panel de admin
3. Verificar que hace clic en el botón de vista de tabla
4. Verificar que procesa las órdenes

## Estado: PENDIENTE DE APROBACIÓN

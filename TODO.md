# TODO: Adapt Binance Monitor to New Admin URL

## Tasks - COMPLETED
- [x] Change URL_ORDENES to "https://c2c-admin.binance.com/es/order/pending"
- [x] Remove order reversal in bucle_principal: change `for target in reversed(nuevas)` to `for target in nuevas`
- [x] Remove order reversal in bucle_envio_lotes: process self.pending_queue directly without reversing
- [x] Remove order reversal in enviar_manual: process self.pending_queue directly without reversing
- [x] Update logs to reflect no reversal (e.g., remove "en orden inverso")
- [x] Fix URL detection: Added support for c2c-admin.binance.com in URL checks
- [x] Fix indentation issue in window handle loop
- [x] Added handling for unknown URLs to continue scanning instead of forcing redirect

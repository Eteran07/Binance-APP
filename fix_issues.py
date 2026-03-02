import re

content = open('Binance_Monitor_V28_Final.py', 'r', encoding='utf-8').read()

# 1. Fix the ID extraction in admin panel - use better pattern
# Find the section in the bucle_principal where we extract IDs for admin
old_pattern = '''                        # Buscar IDs en varios formatos
                        ids_encontrados = re.findall(r'"orderNumber":"(\\d{18,20})"', src)
                        if not ids_encontrados:
                            ids_encontrados = re.findall(r'orderNo=(\\d{18,20})', src)
                        if not ids_encontrados:
                            ids_encontrados = re.findall(r'(\\d{18,20})', src)'''

new_pattern = '''                        # Buscar IDs en formatos específicos del panel admin
                        # Formato: orderNumber en JSON o en URLs
                        ids_encontrados = re.findall(r'"orderNumber":"(\\d{16,20})"', src)
                        if not ids_encontrados:
                            ids_encontrados = re.findall(r'orderNo=(\\d{16,20})', src)
                        if not ids_encontrados:
                            # Buscar números en elementos que parezcan IDs de orden
                            ids_encontrados = re.findall(r'/order/(\\d{16,20})', src)'''

if old_pattern in content:
    content = content.replace(old_pattern, new_pattern)
    print("Replaced ID extraction pattern in admin section")
else:
    print("Pattern not found for admin section")

# 2. Add debug logging for grupos - when sending from admin
old_log = '''                                        # Enviar directamente sin buffer
                                        if self.grupos_alertas:
                                            try:
                                                grupo = self.grupos_alertas[0]'''

new_log = '''                                        # Enviar directamente sin buffer
                                        self.log(f"   📋 [ADMIN] Grupos disponibles: {len(self.grupos_alertas)}")
                                        if self.grupos_alertas:
                                            try:
                                                grupo = self.grupos_alertas[0]
                                                self.log(f"   📋 [ADMIN] Enviando al grupo: {grupo}")'''

if old_log in content:
    content = content.replace(old_log, new_log)
    print("Added debug logging for grupos")
else:
    print("Log pattern not found")

# 3. Also fix the scanning section (escanear_todas_ordenes_admin function)
old_scan = '''                ids_encontrados = re.findall(r'"orderNumber":"(\\d{18,20})"', src)
                if not ids_encontrados:
                    ids_encontrados = re.findall(r'orderNo=(\\d{18,20})', src)
                if not ids_encontrados:
                    ids_encontrados = re.findall(r'(\\d{18,20})', src)'''

new_scan = '''                # Buscar IDs específicos del admin
                ids_encontrados = re.findall(r'"orderNumber":"(\\d{16,20})"', src)
                if not ids_encontrados:
                    ids_encontrados = re.findall(r'orderNo=(\\d{16,20})', src)
                if not ids_encontrados:
                    ids_encontrados = re.findall(r'/order/(\\d{16,20})', src)'''

if old_scan in content:
    content = content.replace(old_scan, new_scan)
    print("Replaced ID extraction in escanear function")
else:
    print("Scan pattern not found")

# 4. Fix the ids_validos filter - change from >= 18 to >= 16
old_filter = '''            ids_validos = [x for x in dict.fromkeys(ids_encontrados) if len(x) >= 18]'''
new_filter = '''            ids_validos = [x for x in dict.fromkeys(ids_encontrados) if len(x) >= 16]'''

if old_filter in content:
    content = content.replace(old_filter, new_filter)
    print("Fixed ids_validos filter")
else:
    print("Filter pattern not found")

# Also fix for the one without dict.fromkeys
old_filter2 = '''            ids_validos = [x for x in dict.fromkeys(ids_encontrados) if len(x) >= 18]'''
new_filter2 = '''            ids_validos = [x for x in dict.fromkeys(ids_encontrados) if len(x) >= 16]'''

if old_filter2 in content:
    content = content.replace(old_filter2, new_filter2)

open('Binance_Monitor_V28_Final.py', 'w', encoding='utf-8').write(content)
print("Done!")

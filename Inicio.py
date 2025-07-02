import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime
import threading
from collections import defaultdict


# Configuración de la página
st.set_page_config(
    page_title="Monitor de Detección de Personas",
    page_icon="👥",
    layout="wide"
)

# Configuración MQTT
MQTT_BROKER = "broker.mqttdashboard.com"
MQTT_PORT = 1883
MQTT_USERNAME = None
MQTT_PASSWORD = None
MQTT_TOPIC = "Npersonas"

# Inicializar variables de estado
if 'mqtt_data' not in st.session_state:
    st.session_state.mqtt_data = {}
if 'detection_grid' not in st.session_state:
    st.session_state.detection_grid = {}
if 'last_update' not in st.session_state:
    st.session_state.last_update = None
if 'mqtt_log' not in st.session_state:
    st.session_state.mqtt_log = []
if 'raw_messages' not in st.session_state:
    st.session_state.raw_messages = []
if 'mqtt_connected' not in st.session_state:
    st.session_state.mqtt_connected = False

# Configuración de la cuadrícula de detección
GRID_WIDTH = 6   # Número de zonas horizontales
GRID_HEIGHT = 4  # Número de zonas verticales
CELL_SIZE = 50   # Tamaño de cada celda en píxeles

def add_mqtt_log(message):
    """Agrega un mensaje al log MQTT con timestamp"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    st.session_state.mqtt_log.append(log_entry)
    # Mantener solo los últimos 50 mensajes
    if len(st.session_state.mqtt_log) > 50:
        st.session_state.mqtt_log.pop(0)
    print(log_entry)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        st.session_state.mqtt_connected = True
        client.subscribe(MQTT_TOPIC)
        add_mqtt_log(f"✅ Conectado a {MQTT_BROKER} y suscrito a {MQTT_TOPIC}")
        try:
            st.rerun()
        except:
            pass
    else:
        st.session_state.mqtt_connected = False
        add_mqtt_log(f"❌ Error al conectar: código {rc}")

def on_message(client, userdata, msg):
    try:
        # Registrar mensaje raw recibido
        raw_payload = msg.payload.decode()
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Agregar a la lista de mensajes raw
        raw_message = {
            'timestamp': timestamp,
            'topic': msg.topic,
            'payload': raw_payload
        }
        st.session_state.raw_messages.append(raw_message)
        # Mantener solo los últimos 20 mensajes
        if len(st.session_state.raw_messages) > 20:
            st.session_state.raw_messages.pop(0)
        
        add_mqtt_log(f"📨 Mensaje recibido en tópico: {msg.topic}")
        add_mqtt_log(f"📝 Payload: {raw_payload[:100]}{'...' if len(raw_payload) > 100 else ''}")
        
        # Decodificar el mensaje MQTT
        data = json.loads(raw_payload)
        st.session_state.mqtt_data = data
        st.session_state.last_update = datetime.now()
        
        # Marcar como conectado si recibimos datos
        st.session_state.mqtt_connected = True
        
        # Procesar detecciones para la cuadrícula
        detections = data.get('detections', [])
        process_detections(detections)
        
        add_mqtt_log(f"✅ Datos procesados: {len(detections)} detecciones de personas")
        
    except json.JSONDecodeError as e:
        add_mqtt_log(f"❌ Error JSON: {str(e)}")
        add_mqtt_log(f"🔍 Payload problemático: {raw_payload}")
    except Exception as e:
        add_mqtt_log(f"❌ Error procesando mensaje: {str(e)}")

def on_disconnect(client, userdata, rc):
    st.session_state.mqtt_connected = False
    add_mqtt_log(f"🔌 Desconectado de MQTT (código: {rc})")

def on_subscribe(client, userdata, mid, granted_qos):
    add_mqtt_log(f"📋 Suscripción confirmada: QoS {granted_qos}")

def on_log(client, userdata, level, buf):
    add_mqtt_log(f"🐛 MQTT Log: {buf}")

def process_detections(detections):
    """Procesa las detecciones y asigna personas a zonas de la cuadrícula"""
    # Limpiar la cuadrícula
    st.session_state.detection_grid = {}
    
    # Configurar resolución de video (ajustar según tu configuración)
    VIDEO_WIDTH = 640
    VIDEO_HEIGHT = 480
    
    for detection in detections:
        x = detection.get('x', 0)
        y = detection.get('y', 0)
        person_id = detection.get('id', 'unknown')
        confidence = detection.get('confidence', 0)
        
        # Convertir coordenadas de píxel a coordenadas de cuadrícula
        grid_x = min(int(x / VIDEO_WIDTH * GRID_WIDTH), GRID_WIDTH - 1)
        grid_y = min(int(y / VIDEO_HEIGHT * GRID_HEIGHT), GRID_HEIGHT - 1)
        
        # Asignar persona a la zona
        cell_key = f"{grid_x},{grid_y}"
        if cell_key not in st.session_state.detection_grid:
            st.session_state.detection_grid[cell_key] = []
        
        st.session_state.detection_grid[cell_key].append({
            'id': person_id,
            'confidence': confidence,
            'original_x': x,
            'original_y': y
        })

def get_mqtt_message():
    """Función para obtener un único mensaje MQTT"""
    message_received = {"received": False, "payload": None}
    
    def on_message(client, userdata, message):
        try:
            payload = json.loads(message.payload.decode())
            message_received["payload"] = payload
            message_received["received"] = True
            add_mqtt_log(f"📨 Mensaje recibido: {str(payload)[:100]}...")
        except Exception as e:
            add_mqtt_log(f"❌ Error al procesar mensaje: {e}")
    
    try:
        client = mqtt.Client()
        client.on_message = on_message
        add_mqtt_log(f"🔄 Conectando a {MQTT_BROKER}:{MQTT_PORT}")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.subscribe(MQTT_TOPIC)
        add_mqtt_log(f"📋 Suscrito a tópico: {MQTT_TOPIC}")
        client.loop_start()
        
        # Esperar hasta 10 segundos por un mensaje
        timeout = time.time() + 10
        while not message_received["received"] and time.time() < timeout:
            time.sleep(0.1)
        
        client.loop_stop()
        client.disconnect()
        add_mqtt_log("🔌 Desconectado del broker")
        
        return message_received["payload"]
    
    except Exception as e:
        add_mqtt_log(f"❌ Error de conexión: {e}")
        return None

def check_mqtt_connection():
    """Verifica el estado de la conexión MQTT"""
    if st.session_state.mqtt_client:
        if not st.session_state.mqtt_connected and st.session_state.last_update:
            # Si recibimos datos en los últimos 30 segundos, consideramos que estamos conectados
            time_diff = (datetime.now() - st.session_state.last_update).total_seconds()
            if time_diff < 30:
                st.session_state.mqtt_connected = True
        
        return st.session_state.mqtt_client.is_connected()
    return False

def create_detection_grid_visualization():
    """Crea la visualización de la cuadrícula de detección de personas"""
    # Crear matriz de densidad de personas
    density_matrix = np.zeros((GRID_HEIGHT, GRID_WIDTH))
    hover_text = np.empty((GRID_HEIGHT, GRID_WIDTH), dtype=object)
    
    # Llenar la matriz con datos de detecciones
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            cell_key = f"{x},{y}"
            if cell_key in st.session_state.detection_grid:
                people_in_zone = st.session_state.detection_grid[cell_key]
                person_count = len(people_in_zone)
                density_matrix[y, x] = person_count
                
                # Crear texto de hover con información de las personas
                person_info = []
                for person in people_in_zone:
                    person_info.append(f"ID: {person['id']} (Conf: {person['confidence']:.2f})")
                
                hover_text[y, x] = f"Zona ({x},{y})<br>Personas: {person_count}<br>" + "<br>".join(person_info)
            else:
                density_matrix[y, x] = 0
                hover_text[y, x] = f"Zona ({x},{y})<br>Personas: 0<br>Estado: Vacía"
    
    # Crear el gráfico con Plotly
    max_people = np.max(density_matrix) if np.max(density_matrix) > 0 else 1
    
    fig = go.Figure(data=go.Heatmap(
        z=density_matrix,
        text=hover_text,
        hovertemplate='%{text}<extra></extra>',
        colorscale='Blues',
        showscale=True,
        colorbar=dict(title="Número de Personas"),
        xgap=4,
        ygap=4,
        zmin=0,
        zmax=max_people
    ))
    
    fig.update_layout(
        title="Mapa de Detección de Personas por Zona",
        xaxis_title="Zona Horizontal",
        yaxis_title="Zona Vertical",
        width=800,
        height=500,
        xaxis=dict(tickmode='linear', tick0=0, dtick=1),
        yaxis=dict(tickmode='linear', tick0=0, dtick=1, autorange='reversed')
    )
    
    return fig

def create_person_count_chart():
    """Crea un gráfico de barras con el conteo de personas por zona"""
    if not st.session_state.detection_grid:
        return None
    
    zones = []
    counts = []
    
    for zone, people in st.session_state.detection_grid.items():
        zones.append(f"Zona {zone}")
        counts.append(len(people))
    
    fig = go.Figure(data=[
        go.Bar(x=zones, y=counts, marker_color='lightblue')
    ])
    
    fig.update_layout(
        title="Conteo de Personas por Zona",
        xaxis_title="Zona",
        yaxis_title="Número de Personas",
        height=400
    )
    
    return fig

def main():
    st.title("👥 Monitor de Detección de Personas")
    st.markdown("### Sistema de Monitoreo en Tiempo Real")
    
    # Sidebar para configuración
    st.sidebar.header("⚙️ Configuración")
    st.sidebar.info(f"🌐 Broker: {MQTT_BROKER}")
    st.sidebar.info(f"📡 Tópico: {MQTT_TOPIC}")
    st.sidebar.info(f"🔲 Cuadrícula: {GRID_WIDTH}x{GRID_HEIGHT} zonas")
    
    # Estado de conexión
    if st.session_state.mqtt_connected:
        st.sidebar.success("🟢 Conectado")
    else:
        st.sidebar.error("🔴 Desconectado")
    
    # Botón principal para obtener datos MQTT
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("📡 Control del Sistema")
        if st.button("🔄 Obtener Datos de Detección", type="primary"):
            with st.spinner('Obteniendo datos del sistema de detección...'):
                mqtt_data = get_mqtt_message()
                
                if mqtt_data:
                    st.session_state.mqtt_data = mqtt_data
                    st.session_state.last_update = datetime.now()
                    
                    # Procesar detecciones
                    detections = mqtt_data.get('detections', [])
                    process_detections(detections)
                    
                    st.success("✅ Datos recibidos correctamente")
                    
                    # Mostrar métricas principales
                    total_people = mqtt_data.get('totalPeople', 0)
                    st.metric("👥 Total Personas", total_people)
                    
                    # Métricas adicionales si están disponibles
                    if 'avgConfidence' in mqtt_data:
                        st.metric("🎯 Confianza Promedio", f"{mqtt_data['avgConfidence']:.2f}")
                    if 'fps' in mqtt_data:
                        st.metric("⚡ FPS", f"{mqtt_data['fps']:.1f}")
                    if 'zones' in mqtt_data:
                        st.metric("🔲 Zonas Activas", mqtt_data['zones'])
                    
                else:
                    st.warning("⚠️ No se recibieron datos del sensor")
        
        # Botón para limpiar logs
        if st.button("🧹 Limpiar Monitor"):
            st.session_state.mqtt_log = []
            st.session_state.raw_messages = []
            st.session_state.mqtt_data = {}
            st.session_state.detection_grid = {}
            add_mqtt_log("🧹 Monitor limpiado")
            st.success("Monitor limpiado")
    
    with col2:
        st.subheader("🗺️ Mapa de Detección")
        
        # Mostrar datos actuales si están disponibles
        if st.session_state.mqtt_data:
            # Mostrar última actualización
            if st.session_state.last_update:
                st.caption(f"📅 Última actualización: {st.session_state.last_update.strftime('%H:%M:%S')}")
            
            # Visualización de la cuadrícula principal
            fig = create_detection_grid_visualization()
            st.plotly_chart(fig, use_container_width=True)
            
            # Información adicional
            total_detected = sum(len(people) for people in st.session_state.detection_grid.values())
            active_zones = len(st.session_state.detection_grid)
            
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("Personas Detectadas", total_detected)
            with col_b:
                st.metric("Zonas Activas", active_zones)
            with col_c:
                density = total_detected / (GRID_WIDTH * GRID_HEIGHT) if total_detected > 0 else 0
                st.metric("Densidad", f"{density:.2f}")
        
        else:
            st.info("🔄 Presiona 'Obtener Datos de Detección' para ver el estado actual")
            st.markdown("""
            **Instrucciones:**
            1. Presiona el botón 'Obtener Datos de Detección'
            2. Los datos se obtendrán del tópico `Npersonas`
            3. El mapa se actualizará automáticamente
            4. Puedes usar el botón 'Probar con datos simulados' para verificar que funciona
            """)
    
    # Botón para probar con datos simulados
    if st.sidebar.button("🧪 Probar con datos simulados"):
        # Datos de prueba para detección de personas
        test_data = {
            'totalPeople': 5,
            'avgConfidence': 0.89,
            'fps': 30.0,
            'zones': 4,
            'detections': [
                {'id': 'P001', 'x': 100, 'y': 120, 'confidence': 0.95},
                {'id': 'P002', 'x': 300, 'y': 200, 'confidence': 0.87},
                {'id': 'P003', 'x': 500, 'y': 150, 'confidence': 0.92},
                {'id': 'P004', 'x': 200, 'y': 350, 'confidence': 0.88},
                {'id': 'P005', 'x': 450, 'y': 400, 'confidence': 0.91}
            ]
        }
        st.session_state.mqtt_data = test_data
        st.session_state.last_update = datetime.now()
        process_detections(test_data['detections'])
        add_mqtt_log("🧪 Datos simulados de detección cargados")
        st.rerun()
    
    # Gráfico adicional de conteo por zona
    if st.session_state.detection_grid:
        st.subheader("📊 Análisis por Zona")
        chart_fig = create_person_count_chart()
        if chart_fig:
            st.plotly_chart(chart_fig, use_container_width=True)
    
    # Mostrar detalles de detecciones si están disponibles
    if st.session_state.mqtt_data and st.session_state.mqtt_data.get('detections'):
        st.subheader("📋 Detalles de Detecciones")
        detections_df = pd.DataFrame(st.session_state.mqtt_data['detections'])
        
        # Agregar información de zona calculada
        if not detections_df.empty:
            detections_df['zona_x'] = (detections_df['x'] / 640 * GRID_WIDTH).astype(int)
            detections_df['zona_y'] = (detections_df['y'] / 480 * GRID_HEIGHT).astype(int)
            detections_df['zona'] = detections_df['zona_x'].astype(str) + ',' + detections_df['zona_y'].astype(str)
        
        st.dataframe(detections_df, use_container_width=True)
    
    # Monitor MQTT expandible
    with st.expander("📡 Monitor MQTT", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📄 Log de Eventos")
            if st.session_state.mqtt_log:
                # Mostrar logs en orden inverso (más recientes primero)
                for log_entry in reversed(st.session_state.mqtt_log[-15:]):
                    st.text(log_entry)
            else:
                st.text("No hay logs disponibles")
        
        with col2:
            st.subheader("📨 Último Mensaje JSON")
            if st.session_state.mqtt_data:
                st.json(st.session_state.mqtt_data)
            else:
                st.text("No se han recibido mensajes")
                st.info(f"Esperando mensajes del tópico: **{MQTT_TOPIC}**")

if __name__ == "__main__":
    main()

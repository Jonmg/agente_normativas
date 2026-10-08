// Utilidades de mapa (Leaflet + OpenStreetMap) y registro de clics para las fichas.
// Los textos se insertan con textContent: nunca HTML que venga de la base de datos.

const CitaMapa = {
  // Si Leaflet no carga (sin conexión, CDN caída) se oculta el mapa y el resto de la página sigue funcionando.
  disponible(id) {
    if (typeof L !== "undefined") return true;
    const caja = document.getElementById(id);
    if (caja) caja.style.display = "none";
    return false;
  },

  crear(id, centro, zoom) {
    const mapa = L.map(id, { scrollWheelZoom: false }).setView(centro || [40.4168, -3.7038], zoom || 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(mapa);
    return mapa;
  },

  chincheta(mapa, lat, lon, color) {
    return L.circleMarker([lat, lon], {
      radius: 11, color: "#fff", weight: 3, fillColor: color || "#0f766e", fillOpacity: 1,
    }).addTo(mapa);
  },

  tarjeta(p) {
    const div = document.createElement("div");
    const fila = (texto, estilo) => {
      const e = document.createElement("div");
      e.textContent = texto;
      if (estilo) e.style.cssText = estilo;
      div.appendChild(e);
    };
    fila(p.nombre, "font-weight:700;font-size:1rem");
    fila(p.tipo + (p.distancia ? " · " + p.distancia : ""), "color:#616e7c");
    fila("Próximo hueco: " + p.proximo, "margin:4px 0");
    const a = document.createElement("a");
    a.href = p.url;
    a.textContent = "Ver huecos y pedir cita →";
    div.appendChild(a);
    return div;
  },

  resultados(id, puntos, yo) {
    if (!puntos.length || !CitaMapa.disponible(id)) return;
    const mapa = CitaMapa.crear(id);
    const limites = [];
    puntos.forEach((p) => {
      CitaMapa.chincheta(mapa, p.lat, p.lon, p.color).bindPopup(CitaMapa.tarjeta(p));
      limites.push([p.lat, p.lon]);
    });
    if (yo) {
      L.circleMarker(yo, { radius: 8, color: "#1d70b8", weight: 3, fillColor: "#fff", fillOpacity: 1 })
        .addTo(mapa).bindTooltip("Tú");
      limites.push(yo);
    }
    if (limites.length === 1) mapa.setView(limites[0], 14);
    else mapa.fitBounds(limites, { padding: [30, 30], maxZoom: 15 });
  },

  // Editor: clic o arrastre para colocar la clínica; rellena los campos lat/lon.
  editor(id, campoLat, campoLon, botonDireccion, textoDireccion, aviso) {
    if (!CitaMapa.disponible(id)) {
      botonDireccion.style.display = "none";
      aviso.textContent = "El mapa no ha podido cargarse. Recarga la página para situar tu clínica.";
      return;
    }
    const lat = parseFloat(campoLat.value), lon = parseFloat(campoLon.value);
    const hay = !isNaN(lat) && !isNaN(lon);
    const mapa = CitaMapa.crear(id, hay ? [lat, lon] : null, hay ? 16 : 6);
    if (!hay) mapa.setView([40.2, -3.7], 6);
    let marca = null;
    const poner = (la, lo, centrar) => {
      campoLat.value = la.toFixed(6);
      campoLon.value = lo.toFixed(6);
      if (!marca) {
        marca = L.marker([la, lo], { draggable: true }).addTo(mapa);
        marca.on("dragend", () => { const p = marca.getLatLng(); poner(p.lat, p.lng); });
      } else marca.setLatLng([la, lo]);
      if (centrar) mapa.setView([la, lo], 17);
    };
    if (hay) poner(lat, lon);
    mapa.on("click", (e) => poner(e.latlng.lat, e.latlng.lng));
    botonDireccion.addEventListener("click", async () => {
      const q = textoDireccion();
      if (!q.trim()) { aviso.textContent = "Escribe primero la dirección, la ciudad y el código postal."; return; }
      aviso.textContent = "Buscando…";
      try {
        const r = await fetch("https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=es&q="
                              + encodeURIComponent(q), { headers: { "Accept-Language": "es" } });
        const datos = await r.json();
        if (!datos.length) { aviso.textContent = "No la encontramos. Pulsa en el mapa para situarla a mano."; return; }
        poner(parseFloat(datos[0].lat), parseFloat(datos[0].lon), true);
        aviso.textContent = "Encontrada. Si no es exacta, arrastra la chincheta. No olvides guardar.";
      } catch (e) {
        aviso.textContent = "No se pudo buscar ahora. Pulsa en el mapa para situarla a mano.";
      }
    });
  },
};

// Clics en llamar / cómo llegar / web: se registran sin frenar la navegación.
document.addEventListener("click", (e) => {
  const enlace = e.target.closest("[data-evento]");
  if (!enlace || !navigator.sendBeacon) return;
  const datos = new FormData();
  datos.append("tipo", enlace.dataset.evento);
  datos.append("_csrf", enlace.dataset.csrf);
  navigator.sendBeacon(enlace.dataset.url, datos);
});

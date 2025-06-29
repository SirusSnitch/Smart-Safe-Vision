// Fonction utilitaire pour afficher un toast avec Toastify
function showToast(message, type = "info") {
  let bgColor = "#007bff"; // bleu info par défaut
  if (type === "success") bgColor = "#28a745"; // vert
  else if (type === "error") bgColor = "#dc3545"; // rouge
  else if (type === "warning") bgColor = "#ffc107"; // jaune

  Toastify({
    text: message,
    duration: 4000,
    close: true,
    gravity: "top",
    position: "right",
    backgroundColor: bgColor,
  }).showToast();
}

// Initialisation de la carte
const map = L.map("map").setView([37.2367, 9.8815], 18);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
}).addTo(map);

L.control.scale({ position: "bottomleft", metric: true }).addTo(map);

// Polygone ISGB
const isgbPolygonGeoJSON = {
  type: "Feature",
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [9.882540055582894, 37.23716617665191],
        [9.880526669259268, 37.236722457011595],
        [9.88096557354379, 37.23552994753754],
        [9.882756024356922, 37.235901568792],
        [9.882978959867387, 37.236140071020344],
        [9.882547022316487, 37.2371606301723],
        [9.882540055582894, 37.23716617665191],
      ],
    ],
  },
  properties: {
    name: "ISGB",
  },
};

L.geoJSON(isgbPolygonGeoJSON, {
  style: { color: "blue", weight: 3, fillOpacity: 0.3 },
}).addTo(map);

const drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

const drawControl = new L.Control.Draw({
  position: "topleft",
  draw: {
    polygon: {
      allowIntersection: false,
      shapeOptions: {
        color: "#ff7800",
        weight: 3,
        fillOpacity: 0.4,
      },
      showArea: true,
    },
    marker: false,
    polyline: false,
    rectangle: false,
    circle: false,
    circlemarker: false,
  },
  edit: {
    featureGroup: drawnItems,
    remove: true,
  },
});
map.addControl(drawControl);

// Événement création polygone
map.on(L.Draw.Event.CREATED, function (event) {
  const layer = event.layer;
  const geojson = layer.toGeoJSON();

  const isInside = turf.booleanWithin(geojson, isgbPolygonGeoJSON);

  if (!isInside) {
    showToast("Zone en dehors du périmètre ISGB !", "error");
    return;
  }

  Swal.fire({
    title: "Nom du département",
    input: "text",
    inputPlaceholder: "Entrez le nom du département",
    showCancelButton: true,
  }).then((result) => {
    if (result.isConfirmed && result.value) {
      const name = result.value;
      const area = (turf.area(geojson) / 10000).toFixed(2); // ha

      const feature = {
        type: "Feature",
        properties: { name, area },
        geometry: geojson.geometry,
      };

      savePolygon(feature).then((id) => {
        if (id) {
          feature.id = id;
          layer.feature = feature;
          layer.bindPopup(`<h4>${name}</h4><p>Superficie : ${area} ha</p>`);
          drawnItems.addLayer(layer);
          showToast("Polygone ajouté avec succès", "success");
        }
      });
    }
  });
});

// Événement édition
map.on(L.Draw.Event.EDITED, function (e) {
  e.layers.eachLayer((layer) => {
    const geojson = layer.toGeoJSON();
    const area = (turf.area(geojson) / 10000).toFixed(2);
    const feature = layer.feature;

    feature.properties.area = area;
    feature.geometry = geojson.geometry;

    updatePolygon(feature).then(() => {
      layer.setPopupContent(
        `<h4>${feature.properties.name}</h4><p>Superficie : ${area} ha</p>`
      );
      showToast("Polygone modifié avec succès", "success");
    });
  });
});

// Événement suppression
map.on(L.Draw.Event.DELETED, function (e) {
  e.layers.eachLayer((layer) => {
    const feature = layer.feature;
    if (feature && feature.id) {
      deletePolygon(feature.id).then((success) => {
        if (success) {
          drawnItems.removeLayer(layer);
          showToast("Polygone supprimé avec succès", "success");
        } else {
          showToast("Erreur lors de la suppression", "error");
        }
      });
    }
  });
});

// Chargement polygones existants
function loadPolygons() {
  fetch("/get-polygons/")
    .then((res) => res.json())
    .then((data) => {
      L.geoJSON(data, {
        style: {
          color: "#ff7800",
          weight: 3,
          fillOpacity: 0.4,
        },
        onEachFeature: (feature, layer) => {
          if (feature.properties?.name) {
            layer.bindPopup(
              `<h4>${feature.properties.name}</h4><p>Superficie : ${
                feature.properties.area || "?"
              } ha</p>`
            );
          }
          layer.feature = { ...feature, id: feature.id };
          drawnItems.addLayer(layer);
        },
      });
    })
    .catch((err) => {
      console.error("Erreur de chargement :", err);
      showToast("Erreur lors du chargement des polygones", "error");
    });
}

// Sauvegarder un polygone
function savePolygon(feature) {
  return fetch("/save-polygon/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      name: feature.properties.name,
      area: feature.properties.area,
      geometry: feature.geometry,
    }),
  })
    .then((res) => res.json())
    .then((data) => data.id)
    .catch((err) => {
      console.error("Erreur ajout :", err);
      showToast("Erreur lors de l'ajout", "error");
      return null;
    });
}

// Mettre à jour un polygone
function updatePolygon(feature) {
  return fetch("/save-polygon/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      id: feature.id,
      name: feature.properties.name,
      area: feature.properties.area,
      geometry: feature.geometry,
    }),
  }).catch((err) => {
    console.error("Erreur modification :", err);
    showToast("Erreur lors de la modification", "error");
  });
}

// Supprimer un polygone
function deletePolygon(id) {
  return fetch(`/delete-polygon/${id}/`, {
    method: "DELETE",
    headers: {
      "X-CSRFToken": getCookie("csrftoken"),
    },
  })
    .then((res) => res.ok)
    .catch((err) => {
      console.error("Erreur suppression :", err);
      showToast("Erreur lors de la suppression", "error");
      return false;
    });
}

// Récupérer le cookie CSRF (Django)
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
}

// Initialisation
loadPolygons();

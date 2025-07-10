const socket = new WebSocket("ws://127.0.0.1:8000/ws/camera/");

socket.onopen = () => {
  console.log("WebSocket connecté");
  socket.send("Bonjour du client !");
};

socket.onmessage = (event) => {
  console.log("Message reçu du serveur:", event.data);
};

socket.onclose = () => {
  console.log("WebSocket fermé");
};

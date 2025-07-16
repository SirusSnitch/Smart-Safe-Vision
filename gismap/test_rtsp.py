import cv2

rtsp_url = 'rtsp://192.168.1.17:8554/cam2'

cap = cv2.VideoCapture(rtsp_url)

if not cap.isOpened():
    print("Erreur : Impossible d'ouvrir le flux RTSP")
    exit(1)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Erreur : Frame non reçue")
        break
    cv2.imshow("Flux RTSP", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

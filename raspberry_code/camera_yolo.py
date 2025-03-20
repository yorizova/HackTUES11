import cv2
from ultralytics import YOLO

cap = cv2.VideoCapture(0)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1280)

model = YOLO("my_module_ncnn_module")

while True:
    ret, frame = cap.read()
    results = model(frame, imgsz=640)

    annotated_frame = results[0].plot()

    inference_time = results[0].speed['inference']
    fps = 1000 / inference_time
    text = f'FPS: {fps:.1f}'

    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(text, font, 1, 2)[0]
    text_x = annotated_frame.shape[1] - text_size[0] - 10
    text_y = text_size[1] + 10

    cv2.putText(annotated_frame, text, (text_x, text_y), font, 1, (255, 255, 255), 2, cv2.LINE_AA)

    cv2.imshow("Camera", annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
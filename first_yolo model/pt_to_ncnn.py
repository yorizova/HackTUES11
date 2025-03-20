from ultralytics import YOLO

model = YOLO('my_model.pt')
model.export(format="ncnn")

ncnn_module = YOLO("my_module_ncnn_module")
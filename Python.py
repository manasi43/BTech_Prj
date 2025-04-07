
import cv2
import os
import time
import sqlite3
import serial  # Serial communication with Arduino
from ultralytics import YOLO
import pytesseract
import re

# Initialize Serial Communication (Update COM port for Windows or /dev/ttyUSBx for Linux)
arduino = serial.Serial(port="COM3", baudrate=9600, timeout=1)
time.sleep(2)

# Load YOLO models
object_model = YOLO("yolov8n.pt")  # Pretrained YOLO model for vehicle detection
plate_model = YOLO("models/best.pt")  # Custom-trained license plate detection model

# Create directories
car_folder = "car_images"
plate_folder = "plates"
os.makedirs(car_folder, exist_ok=True)
os.makedirs(plate_folder, exist_ok=True)

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

STATE_CODES = ["AP", "AR", "AS", "BR", "CG", "GA", "GJ", "HR", "HP", "JH", "KA", "KL", "MP", "MH", "MN", "ML", "MZ",
               "NL", "OD", "PB", "RJ", "SK", "TN", "TS", "TR", "UK", "UP", "WB", "AN", "CH", "DN", "DD", "DL", "JK",
               "LA", "LD", "PY"]

def find_nearest_state_code(detected_code):
    detected_code = detected_code.upper()
    if detected_code in STATE_CODES:
        return detected_code
    return min(STATE_CODES, key=lambda x: sum(a != b for a, b in zip(detected_code, x)))


def preprocess_plate(plate_crop):
    gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, 11, 2)
    return gray

def clean_plate(plate_text):
    plate_text = plate_text.upper()
    plate_text = re.sub(r"[^A-Z0-9]", "", plate_text)
    plate_text = re.sub(r'(?<=[0-9])O(?=[0-9])', '0', plate_text)
    if len(plate_text) >= 2:
        plate_text = find_nearest_state_code(plate_text[:2]) + plate_text[2:]
    return plate_text

def is_valid_indian_plate(plate_text):
    pattern = r"^[A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{4}$"
    return re.match(pattern, plate_text) is not None

def check_plate_in_db(plate_number):
    cleaned_plate = clean_plate(plate_number)
    if not is_valid_indian_plate(cleaned_plate):
        print(f"Ignored invalid plate format: {cleaned_plate}")
        return None

    conn = sqlite3.connect("parking_system.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM registered_vehicles WHERE plate_number = ?", (cleaned_plate,))
    result = cursor.fetchone()
    conn.close()

    if result:
        assigned_slot = result[0]
        print(f"Plate {cleaned_plate} is REGISTERED. Assigned Slot: {assigned_slot}, Owner - {result[2]}, Contact No - {result[3]}")
        return assigned_slot
    else:
        print(f"Plate {cleaned_plate} is NOT REGISTERED!")
        return None

def start_camera():
    cap = cv2.VideoCapture(0)
    unregistered_timeout = 30  # Maximum time limit for unregistered vehicles (in seconds)
    start_time = time.time()
    attempt_count = 0
    max_attempts = 10  # Allow 10 attempts before stopping detection
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
         # Step 1: Object Detection (detect all objects including cars)
        results = object_model(frame)
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cls_id = int(box.cls)
                label = object_model.names[cls_id]
                confidence = box.conf.item()

                 # Draw bounding box for all detected objects
                color = (0, 255, 0)  # Green for objects
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{label} {confidence:.2f}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


                # If detected object is a car, process it for license plate detection 
                if label == "car" and confidence > 0.3:
                    car_crop = frame[y1:y2, x1:x2]
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    car_filename = os.path.join(car_folder, f"car_{timestamp}.jpg")
                    cv2.imwrite(car_filename, car_crop)


                     # Step 2: License Plate Detection (on the cropped car)
                    plate_results = plate_model(car_crop)
                    for p_result in plate_results:
                        for p_box in p_result.boxes:
                            px1, py1, px2, py2 = map(int, p_box.xyxy[0])
                            plate_crop = car_crop[py1:py2, px1:px2]
                            plate_filename = os.path.join(plate_folder, f"plate_{timestamp}.jpg")
                            cv2.imwrite(plate_filename, plate_crop)
                            print(f"License Plate Saved: {plate_filename}")

                            # Draw bounding box around detected license plate
                            plate_color = (0, 0, 255)  # Red for license plates
                            cv2.rectangle(frame, (x1 + px1, y1 + py1), (x1 + px2, y1 + py2), plate_color, 2)
                            cv2.putText(frame, "License Plate", (x1 + px1, y1 + py1 - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, plate_color, 2)

                            # # Step 3: OCR on License Plate 
                            preprocessed_plate = preprocess_plate(plate_crop)
                            plate_text = pytesseract.image_to_string(preprocessed_plate, config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
                            cleaned_plate = clean_plate(plate_text.strip())
                            assigned_slot = check_plate_in_db(cleaned_plate)

                            if not is_valid_indian_plate(cleaned_plate):
                                print(f"Ignored: {cleaned_plate} (Invalid Format)")
                                continue

                            print(f"Recognized License Plate: {cleaned_plate}")
                            
                            if assigned_slot:
                                print("Registered vehicle detected, opening barricade and stopping camera.")
                                print("Sending command: OPEN_BARRICADE")
                                arduino.write(f"OPEN_BARRICADE\r\n".encode())
                                arduino.flush()
                                print("Waiting for parking confirmation...")
                                time.sleep(1)  # Wait for the car to pass
                                cap.release()
                                cv2.destroyAllWindows()
                                monitor_parking(cleaned_plate, assigned_slot)
                                return  # Exit function
                            else:
                                attempt_count += 1
                                print(f"Attempt {attempt_count}/{max_attempts} for unregistered vehicle.")

                                if attempt_count >= max_attempts or (time.time() - start_time) > unregistered_timeout:
                                    print("Max attempts reached or timeout occurred. Stopping camera.")
                                    arduino.write(b"CLOSE_BARRICADE\r\n")
                                    time.sleep(1)  # Give Arduino time to process the command
                                    cap.release()
                                    cv2.destroyAllWindows()
                                    return  # Exit function

        
        cv2.imshow("Vehicle Detection", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()

def monitor_parking(plate_number, assigned_slot):
    print(f"Monitoring slot {assigned_slot} for {plate_number}...")
    while True:
        if arduino.in_waiting > 0:
            sensor_data = arduino.readline().decode('utf-8').strip()
            print("Arduino Response:", sensor_data)
            if "SLOT_OCCUPIED:" in sensor_data:
                print(sensor_data)
                
                occupied_slot = sensor_data.split(":")[1]
                if occupied_slot == assigned_slot:
                    print(f"Car {plate_number} is correctly parked in slot {assigned_slot}.")
                    return
                else:
                    print(f"ALERT! Car {plate_number} parked in wrong slot {occupied_slot} instead of {assigned_slot}.")
                    arduino.write(f"WRONG_SLOT_ALERT:{plate_number}:{occupied_slot}\r\n".encode())
                    return

while True:
    if arduino.in_waiting > 0:
        command = arduino.readline().decode('utf-8').strip()
        if command == "START_CAMERA":
            print("Motion detected! Starting Camera...")
            start_camera()
#include <Servo.h>
Servo barricade;  
int IR = 4;      
int motor = 3;    
int val;          

// Ultrasonic sensor setup for parking slots
const int num_slots = 2;  // Adjust based on your parking slots
const int trigPins[num_slots] = {7, 9};   // Trig pins for 101, 102
const int echoPins[num_slots] = {6, 8};  // Echo pins for 101, 102
const char* slot_labels[num_slots] = {"101", "102"};

// Exit IR Sensor
int exitIR = 5;
int exitVal;

void setup() {
    Serial.begin(9600);
    pinMode(IR, INPUT);
    pinMode(exitIR, INPUT);
   
    barricade.attach(motor);
    barricade.write(0);  // Ensure barricade starts at closed position
    delay(1000);

    for (int i = 0; i < num_slots; i++) {
    pinMode(trigPins[i], OUTPUT);
    pinMode(echoPins[i], INPUT);
    }

}

long measureDistance(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH);
  return duration * 0.034 / 2;  // Convert to cm
}


void loop() {
    int entryVal = digitalRead(IR);
    int exitVal = digitalRead(exitIR);

    // Step 1: Detect motion at entrance and trigger camera
    if (entryVal == 0) {  
        Serial.println("Motion detected");
        Serial.println("START_CAMERA");  
        delay(5000);  
    }
        // Step 2: Handle barricade 
    if (Serial.available() > 0) {
      String data = Serial.readString();
      data.trim();

        if (data == "OPEN_BARRICADE") {
          Serial.println("Registered vehicle. Opening Barricade.");
          openBarricade();
        }
        else if (data == "CLOSE_BARRICADE") {
          Serial.println("Unregistered vehicle. Barricade remains closed.");
          barricade.write(0);
        }
        
    }
    delay(1000);

    // Step 3: Detect exit and open barricade
    if (exitVal == 0) {  
      Serial.println("Exit detected");
      Serial.println("OPEN_BARRICADE");
      openBarricade();
    }

    // Step 4: Check if cars are parked correctly
    for (int i = 0; i < num_slots; i++) {
      long distance = measureDistance(trigPins[i], echoPins[i]);
    
      if (distance >= 1 && distance < 5) {  // Detects a car within 40cm
      Serial.print("SLOT_OCCUPIED:");  Serial.println(slot_labels[i]);
      delay(5000);
      }
    }
}

    
    

void openBarricade() {
    for (int angle = 0; angle <= 90; angle++) {  
        barricade.write(angle);
        delay(100);
    }
    delay(5000);  // Keep open for 5 seconds

    for (int angle = 90; angle >= 0; angle--) {  
        barricade.write(angle);
        delay(100);
    }
}
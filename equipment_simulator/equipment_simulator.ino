#include <Arduino.h>

// Параметры станка
float temperature = 25.0;
float pressure = 1.0;
float vibration = 0.5;
int spindle_speed = 1500;
int load = 30;
bool isRunning = false;
unsigned long startTime = 0;
unsigned long totalRuntime = 0;

void setup() {
  Serial.begin(9600);
  while (!Serial) {
    ; // Ожидание подключения
  }
  Serial.setTimeout(50);
  randomSeed(analogRead(0));
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.println("STATUS: Система готова");
}

void processCommand(String command) {
  command.trim();
  
  if (command == "START") {
    if (!isRunning) {
      isRunning = true;
      startTime = millis();
      // Инициализация значений с более активными изменениями
      temperature = 30.0;
      pressure = 1.2;
      vibration = 0.6;
      spindle_speed = 1800;
      load = 40;
      Serial.println("STATUS: Станок запущен");
      Serial.print("STARTTIME:");
      Serial.println(startTime);
    }
  } 
  else if (command == "STOP") {
    if (isRunning) {
      isRunning = false;
      totalRuntime += millis() - startTime;
      Serial.println("STATUS: Станок остановлен");
      Serial.print("STOPTIME:");
      Serial.println(millis());
    }
  }
  else if (command == "GETDATA") {
    if (isRunning) {
      // Более активное изменение параметров
      temperature += random(-20, 30) / 10.0;
      temperature = constrain(temperature, 20.0, 100.0);
      
      pressure += random(-15, 15) / 10.0;
      pressure = constrain(pressure, 0.5, 2.5);
      
      vibration += random(-10, 10) / 10.0;
      vibration = constrain(vibration, 0.1, 2.0);
      
      spindle_speed += random(-200, 200);
      spindle_speed = constrain(spindle_speed, 1000, 3000);
      
      load += random(-20, 20);
      load = constrain(load, 10, 100);
      
      // Проверка критических значений
      if (temperature > 80) {
        Serial.println("ALERT: Высокая температура!");
      }
      if (pressure > 2.0) {
        Serial.println("ALERT: Высокое давление!");
      }
      if (vibration > 1.5) {
        Serial.println("ALERT: Сильная вибрация!");
      }
      
      // Отправка данных
      Serial.print(temperature, 1);
      Serial.print(",");
      Serial.print(pressure, 1);
      Serial.print(",");
      Serial.print(vibration, 1);
      Serial.print(",");
      Serial.print(spindle_speed);
      Serial.print(",");
      Serial.println(load);
    } else {
      Serial.println("0,0,0,0,0");
    }
  }
  else if (command == "GETSTATS") {
    Serial.print("STATS:");
    Serial.print(totalRuntime + (isRunning ? (millis() - startTime) : 0));
    Serial.print(",");
    Serial.println(isRunning ? 1 : 0);
  }
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    processCommand(command);
  }
  
  // Медленное "дыхание" LED при работе
  if (isRunning) {
    static unsigned long lastBlink = 0;
    static bool ledState = false;
    if (millis() - lastBlink > 1000) {
      ledState = !ledState;
      digitalWrite(LED_BUILTIN, ledState);
      lastBlink = millis();
    }
  } else {
    digitalWrite(LED_BUILTIN, LOW);
  }
  
  delay(50);
}
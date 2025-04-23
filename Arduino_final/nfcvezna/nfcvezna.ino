#include <SPI.h>
#include <PN532_SPI.h>
#include <PN532.h>
#include <HX711_ADC.h>

// System states
enum SystemMode {
  WEIGHING_MODE,
  PAYMENT_MODE
};
SystemMode currentMode = WEIGHING_MODE;

// HX711 Pins (using pin 2 for interrupt compatibility)
const int HX711_dout = 2;  // Must be interrupt-capable pin
const int HX711_sck = 5;
HX711_ADC LoadCell(HX711_dout, HX711_sck);
const int calVal_eepromAdress = 0;
volatile bool hx711_data_ready = false;
unsigned long t = 0;

// NFC Module Pins
#define PN532_SCK  (13)
#define PN532_MOSI (11)
#define PN532_MISO (12)
#define PN532_SS   (10)

PN532_SPI pn532spi(SPI, PN532_SS);
PN532 nfc(pn532spi);

const String DESTINATION_ACCOUNT = "BANK-001";
const float TRANSACTION_FEE = 1.00;

enum TransactionState {
  AUTH_REQUIRED,
  AMOUNT_PENDING,
  SOURCE_PENDING,
  ACCOUNT_PENDING
};

struct BankAccount {
  String accountNumber;
  float balance;
};

struct NFCCard {
  uint8_t uid[7];
  uint8_t uidLength;
  String linkedAccount;
};

BankAccount accounts[] = {
  {"USER-123", 1000.00},
  {"USER-456", 500.00},
  {DESTINATION_ACCOUNT, 100000.00}
};

NFCCard registeredCards[] = {
  {{0x4E, 0xF2, 0xB5, 0x02}, 4, "USER-123"}
};

TransactionState txState = AUTH_REQUIRED;
float transactionAmount = 0.0;
String sourceAccount = "";
float currentWeight = 0.0;
bool transactionInProgress = false;  // Flag to prevent multiple scans

// ISR for HX711
void hx711ISR() {
  hx711_data_ready = true;
}

// Function prototypes
void handleSerialInput();
void enterPaymentMode();
void exitPaymentMode();
void handlePaymentProcess();
void printUID(uint8_t *uid, uint8_t length);
void handleCardScan(uint8_t *uid, uint8_t uidLength);
bool checkAuthCard(uint8_t *uid, uint8_t length);
bool checkPaymentCard(uint8_t *uid, uint8_t length);
void processTransaction();
BankAccount* findAccount(String accountNumber);
bool compareUID(uint8_t *uid1, uint8_t len1, uint8_t *uid2, uint8_t len2);

void setup() {
  Serial.begin(115200);
  delay(10);
  Serial.println("Initializing System...");

  // Initialize Load Cell
  LoadCell.begin();
  float calibrationValue = 696.0;
  // EEPROM.get(calVal_eepromAdress, calibrationValue);

  Serial.println("Starting Load Cell...");
  LoadCell.start(2000, true);  // Let it settle for 2 seconds

  if (LoadCell.getTareTimeoutFlag()) {
    Serial.println("HX711 Connection Error!");
    while (1);
  } else {
    while (!LoadCell.update()); // Ensure it's stable
    LoadCell.setCalFactor(calibrationValue);
    LoadCell.tare(); // Tare only after stabilization
    Serial.println("Load Cell Ready and Tared.");
  }

  // Initialize NFC
  nfc.begin();
  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println("PN532 not found!");
    while (1);
  }
  nfc.SAMConfig();
  Serial.println("System Ready");
  Serial.println("Type 'checkout' to begin payment process");
  Serial.println("Type 't' to tare the scale");
}


void loop() {
  static boolean newDataReady = false;
  const int serialPrintInterval = 500;
  static unsigned long zeroDriftTimer = 0;
  static bool recentlyWeighed = false;

  if (currentMode == WEIGHING_MODE) {
    if (LoadCell.update()) {
      newDataReady = true;
    }

    if (newDataReady && (millis() > t + serialPrintInterval)) {
      currentWeight = LoadCell.getData();

      // Filter out small fluctuations
      if (abs(currentWeight) > 1.0) {
        Serial.print("Weight: ");
        Serial.print(currentWeight, 1);
        Serial.println(" g");
        recentlyWeighed = true;
        zeroDriftTimer = millis();  // Reset zero timer
      } else {
        // If weight was recently present and now is low, check how long it's been low
        if (recentlyWeighed && (millis() - zeroDriftTimer > 3000)) {
          Serial.println("Auto-zeroing scale...");
          LoadCell.tareNoDelay();  // Smooth auto-zero
          recentlyWeighed = false;
        }
      }

      newDataReady = false;
      t = millis();
    }
  } 
  else if (currentMode == PAYMENT_MODE) {
    handlePaymentProcess();
  }

  handleSerialInput();

  if (LoadCell.getTareStatus()) {
    Serial.println("Tare complete");
  }
}


void handleSerialInput() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();

    if (input.equalsIgnoreCase("checkout")) {
      if (currentMode == WEIGHING_MODE) {
        enterPaymentMode();
      } else {
        Serial.println("Already in payment mode");
      }
    } 
    else if (input.equalsIgnoreCase("t")) {
      LoadCell.tareNoDelay();
      Serial.println("Tare started...");
    }
    else if (input.startsWith("AMOUNT:")) {
      if (currentMode == PAYMENT_MODE && txState == AMOUNT_PENDING) {
        transactionAmount = input.substring(7).toFloat();
        if (transactionAmount > 0) {
          Serial.print("Amount set to: $");
          Serial.println(transactionAmount, 2);
          Serial.println("Now scan your payment card");
          txState = SOURCE_PENDING;
        } else {
          Serial.println("Amount must be greater than 0");
        }
      }
    }
    else if (input.startsWith("ACCOUNT:")) {
      if (currentMode == PAYMENT_MODE && txState == ACCOUNT_PENDING) {
        sourceAccount = input.substring(8);
        if (sourceAccount.length() > 0) {
          processTransaction();
        } else {
          Serial.println("Account cannot be empty");
        }
      }
    }
  }

  if (LoadCell.getTareStatus()) {
    Serial.println("Tare complete");
  }
}

void enterPaymentMode() {
  currentMode = PAYMENT_MODE;
  Serial.println("\n=== ENTERING PAYMENT MODE ===");
  Serial.println("Place your auth card on the NFC reader");
  txState = AUTH_REQUIRED;
}


void exitPaymentMode() {
  currentMode = WEIGHING_MODE;
  txState = AUTH_REQUIRED;
  transactionAmount = 0.0;
  sourceAccount = "";
  Serial.println("\n=== RETURNING TO WEIGHING MODE ===");
}

void handlePaymentProcess() {
  uint8_t uid[7];
  uint8_t uidLength;

  if (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength)) {
    Serial.println("\nCard Detected!");
    printUID(uid, uidLength);

    if (!transactionInProgress) {
      transactionInProgress = true;  // Mark transaction as in progress
      handleCardScan(uid, uidLength);
    } else {
      Serial.println("Transaction already in progress, please wait.");
    }

    delay(1000);  // Delay to prevent rapid re-scanning
  }
}

void printUID(uint8_t *uid, uint8_t length) {
  Serial.print("UID: ");
  for (uint8_t i = 0; i < length; i++) {
    Serial.print("0x"); 
    Serial.print(uid[i], HEX);
    Serial.print(" ");
  }
  Serial.println();
}

void handleCardScan(uint8_t *uid, uint8_t uidLength) {
  Serial.print("Scanned UID Length: ");
  Serial.println(uidLength);
  switch (txState) {
    case AUTH_REQUIRED:
      if (checkAuthCard(uid, uidLength)) {
        txState = AMOUNT_PENDING;
        Serial.println("Authorization Successful!");
        //Serial.println("Enter amount via Serial (AMOUNT:XX.XX)");
      } else {
        Serial.println("Unauthorized Card!");
        transactionInProgress = false;  // Reset flag if unauthorized
      }
      break;
    case SOURCE_PENDING:
      if (checkPaymentCard(uid, uidLength)) {
        txState = ACCOUNT_PENDING;
        Serial.println("Payment card scanned. Enter source account (ACCOUNT:XXXX)");
      }
      break;
  }
}

bool checkAuthCard(uint8_t *uid, uint8_t length) {
  for (auto &card : registeredCards) {
    if (compareUID(uid, length, card.uid, card.uidLength)) {
      return card.linkedAccount == "USER-123";
    }
  }
  return false;
}

bool checkPaymentCard(uint8_t *uid, uint8_t length) {
  // Add your payment card validation logic here
  return true; // For now, accept any card as payment card
}

void processTransaction() {
  BankAccount *src = findAccount(sourceAccount);
  BankAccount *dst = findAccount(DESTINATION_ACCOUNT);

  if (!src || !dst) {
    Serial.println("Account error!");
    Serial.println("DECLINED");
    transactionInProgress = false;  // Reset flag after failed transaction
    return;
  }

  float totalAmount = transactionAmount + TRANSACTION_FEE;

  Serial.print("Source account balance: $");
  Serial.println(src->balance, 2);
  Serial.print("Transaction amount: $");
  Serial.println(transactionAmount, 2);
  Serial.print("Total amount with fee: $");
  Serial.println(totalAmount, 2);

  if (src->balance >= totalAmount) {
    src->balance -= totalAmount;
    dst->balance += transactionAmount;

    Serial.println("\n=== TRANSACTION RECEIPT ===");
    Serial.print(" From: "); Serial.println(sourceAccount);
    Serial.print(" To: "); Serial.println(DESTINATION_ACCOUNT);
    Serial.print(" Amount: $"); Serial.println(transactionAmount, 2);
    Serial.print(" Fee: $"); Serial.println(TRANSACTION_FEE, 2);
    Serial.print(" Total: $"); Serial.println(totalAmount, 2);
    Serial.print(" New Balance: $"); Serial.println(src->balance, 2);
    Serial.println("===========================");

    Serial.println("APPROVED");
  } else {
    Serial.println("Transaction declined: Insufficient funds");
    Serial.println("DECLINED");
  }

  // Reset after transaction is processed
  transactionInProgress = false;  // Reset flag after transaction is complete
  exitPaymentMode();
}

BankAccount* findAccount(String accountNumber) {
  for (auto &acc : accounts) {
    if (acc.accountNumber == accountNumber) return &acc;
  }
  return nullptr;
}

bool compareUID(uint8_t *uid1, uint8_t len1, uint8_t *uid2, uint8_t len2) {
  if (len1 != len2) return false;
  for (uint8_t i = 0; i < len1; i++) {
    if (uid1[i] != uid2[i]) return false;
  }
  return true;
}

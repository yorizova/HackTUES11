#include <SoftwareSerial.h>
#include <PN532_SWHSU.h>
#include <PN532.h>

SoftwareSerial SWSerial(10, 11);
PN532_SWHSU pn532swhsu(SWSerial);
PN532 nfc(pn532swhsu);

// Fixed destination account
const String DESTINATION_ACCOUNT = "BANK-001";
const float TRANSACTION_FEE = 1.00;

enum TransactionState {
  AUTH_REQUIRED,
  AMOUNT_PENDING,
  SOURCE_PENDING,
  TX_COMPLETED
};

// Forward declarations
bool checkAuthCard(uint8_t *uid, uint8_t length);
bool getLinkedAccount(uint8_t *uid, uint8_t length, String &account);
void processTransaction();
bool compareUID(uint8_t *uid1, uint8_t len1, uint8_t *uid2, uint8_t len2);
void printUID(uint8_t *uid, uint8_t length);
void resetSystem();
void printInstructions();

// Structures
struct BankAccount {
  String accountNumber;
  float balance;
};

struct NFCCard {
  uint8_t uid[7];
  uint8_t uidLength;
  String linkedAccount;
};

// Simulated database
BankAccount accounts[] = {
  {"USER-123", 1000.00},
  {"USER-456", 500.00},
  {DESTINATION_ACCOUNT, 100000.00}
};

NFCCard registeredCards[] = {
  {{0x4E, 0xF2, 0xB5, 0x2}, 4, "USER-123"},  // Authorization card
  {{0x5, 0x8F, 0xB0, 0x6F, 0x7F, 0xE2, 0x0 }, 7, "USER-456"}  // Payment card
};

TransactionState txState = AUTH_REQUIRED;
float transactionAmount = 0.0;
String sourceAccount = "";

void setup() {
  Serial.begin(115200);
  while (!Serial); // Wait for serial port
  
  nfc.begin();
  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println("PN532 not found!");
    while(1);
  }
  
  nfc.SAMConfig();
  Serial.println("System Ready - Scan Auth Card");
  printInstructions();
}

void loop() {
  uint8_t uid[7];
  uint8_t uidLength;

  if (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength)) {
    Serial.println("\nCard Detected!");
    printUID(uid, uidLength);
    handleCardScan(uid, uidLength);
    delay(2000);
  }
}

void handleCardScan(uint8_t *uid, uint8_t uidLength) {
  switch(txState) {
    case AUTH_REQUIRED:
      if (checkAuthCard(uid, uidLength)) {
        txState = AMOUNT_PENDING;
        Serial.println("Authorization Successful!");
        Serial.println("Enter amount via Serial (AMOUNT:XX.XX)");
      } else {
        Serial.println("Unauthorized Card!");
      }
      break;

    case SOURCE_PENDING:
      if (getLinkedAccount(uid, uidLength, sourceAccount)) {
        processTransaction();
        txState = TX_COMPLETED;
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

bool getLinkedAccount(uint8_t *uid, uint8_t length, String &account) {
  for (auto &card : registeredCards) {
    if (compareUID(uid, length, card.uid, card.uidLength)) {
      account = card.linkedAccount;
      Serial.print("Source account selected: ");
      Serial.println(account);
      return true;
    }
  }
  return false;
}

void processTransaction() {
  BankAccount *src = findAccount(sourceAccount);
  BankAccount *dst = findAccount(DESTINATION_ACCOUNT);

  if (!src || !dst) {
    Serial.println("Account error!");
    return;
  }

  float totalAmount = transactionAmount + TRANSACTION_FEE;

  if (src->balance >= totalAmount) {
    src->balance -= totalAmount;
    dst->balance += transactionAmount;
    
    Serial.println("\n=== Transaction Receipt ===");
    Serial.print(" From:      "); Serial.println(sourceAccount);
    Serial.print(" To:        "); Serial.println(DESTINATION_ACCOUNT);
    Serial.print(" Amount:    $"); Serial.println(transactionAmount);
    Serial.print(" Fee:       $"); Serial.println(TRANSACTION_FEE);
    Serial.print(" Total:     $"); Serial.println(totalAmount);
    Serial.print(" New Balance: $"); Serial.println(src->balance);
    Serial.println("===========================");
  } else {
    Serial.println("Transaction declined: Insufficient funds");
  }
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

void serialEvent() {
  while (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    if (input.startsWith("AMOUNT:")) {
      transactionAmount = input.substring(7).toFloat();
      if (txState == AMOUNT_PENDING) {
        txState = SOURCE_PENDING;
        Serial.print("Amount set: $");
        Serial.println(transactionAmount);
        Serial.println("Scan PAYMENT CARD");
      }
    }
  }
}

void resetSystem() {
  txState = AUTH_REQUIRED;
  transactionAmount = 0.0;
  sourceAccount = "";
  Serial.println("\nSystem reset. Ready for new transaction.");
  printInstructions();
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

void printInstructions() {
  Serial.println("\n=== Transaction Flow ===");
  Serial.println("1. Scan AUTHORIZED card");
  Serial.println("2. Enter amount via Serial Monitor");
  Serial.println("3. Scan SOURCE payment card");
  Serial.println("4. Transaction auto-completes to bank");
  Serial.print("Fixed Destination: ");
  Serial.println(DESTINATION_ACCOUNT);
  Serial.println("========================");
}
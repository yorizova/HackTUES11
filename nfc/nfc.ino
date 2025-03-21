
#include <SoftwareSerial.h>

#include <PN532_SWHSU.h>

#include <PN532.h>

SoftwareSerial SWSerial( 10, 11 ); // RX, TX

PN532_SWHSU pn532swhsu( SWSerial );

PN532 nfc( pn532swhsu );


void setup(void) {

  Serial.begin(115200);

  Serial.println("Hello Maker!");

  nfc.begin();

  uint32_t versiondata = nfc.getFirmwareVersion();

  if (! versiondata) {

    Serial.print("Didn't Find PN53x Module");

    while (1); // Halt

  }


  Serial.print("Found chip PN5"); Serial.println((versiondata>>24) & 0xFF, HEX);

  Serial.print("Firmware ver. "); Serial.print((versiondata>>16) & 0xFF, DEC);

  Serial.print('.'); Serial.println((versiondata>>8) & 0xFF, DEC);


  nfc.SAMConfig();

  Serial.println("Waiting for an ISO14443A Card ...");

}

void loop(void) {

  boolean success;

  uint8_t uid[] = { 0, 0, 0, 0, 0, 0, 0 };  

  uint8_t uidLength;                       

success = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, &uid[0], &uidLength);

  if (success) {

    Serial.println("Found A Card!");

    Serial.print("UID Length: ");Serial.print(uidLength, DEC);Serial.println(" bytes");

    Serial.print("UID Value: ");

    for (uint8_t i=0; i < uidLength; i++)

    {

      Serial.print(" 0x");Serial.print(uid[i], HEX);

    }

    Serial.println("");

    

    delay(2000);

  }

  else

  {

    

    Serial.println("Timed out! Waiting for a card...");

  }
}
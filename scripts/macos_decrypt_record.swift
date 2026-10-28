// Private subprocess protocol for an authenticated in-memory capture consumer; not a display command.
// Inputs: prepared local recipient directory, ciphertext-file path and externally pinned public PEM hash.
// Outputs: authenticated plaintext bytes on a private stdout pipe only after CMS success; no secret logging.
import Foundation
import Security
import CryptoKit
import Darwin

let arguments = CommandLine.arguments
guard arguments.count == 4 else { exit(2) }
let directory = URL(fileURLWithPath: arguments[1], isDirectory: true)
let ciphertext = URL(fileURLWithPath: arguments[2])
let expectedPin = arguments[3]

do {
    // Restrict the lookup to this application's dedicated local recipient namespace.
    let metadataData = try Data(contentsOf: directory.appendingPathComponent("recipient-metadata.json"))
    guard let metadata = try JSONSerialization.jsonObject(with: metadataData) as? [String: Any],
          metadata["status"] as? String == "local_recipient_prepared",
          metadata["keychain_service"] as? String == "org.dissertation.evidence.recipient",
          let account = metadata["keychain_account"] as? String, UUID(uuidString: account) != nil,
          metadata["private_key_encrypted"] as? Bool == true,
          metadata["keychain_sync"] as? Bool == false,
          metadata["recipient_public_pem_sha256"] as? String == expectedPin else { exit(1) }
    let certificate = directory.appendingPathComponent("recipient-public.pem")
    let key = directory.appendingPathComponent("private-key.encrypted.pem")
    let publicData = try Data(contentsOf: certificate)
    let actualPin = SHA256.hash(data: publicData).map { String(format: "%02x", $0) }.joined()
    guard actualPin == expectedPin else { exit(1) }
    let encryptedKey = try Data(contentsOf: key)
    guard String(data: encryptedKey.prefix(100), encoding: .utf8)?.contains("ENCRYPTED PRIVATE KEY") == true else { exit(1) }
    let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "org.dissertation.evidence.recipient", kSecAttrAccount as String: account,
        kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
    var value: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &value) == errSecSuccess,
          let passphrase = value as? Data else { exit(1) }
    // Pass the unlock secret only through stdin. Suppress provider diagnostics and retain output
    // in memory until OpenSSL has authenticated the complete CMS record successfully.
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/opt/homebrew/opt/openssl@3/bin/openssl")
    process.arguments = ["cms", "-decrypt", "-binary", "-inform", "DER", "-in", ciphertext.path,
        "-recip", certificate.path, "-inkey", key.path, "-passin", "stdin"]
    let source = Pipe(), output = Pipe()
    process.standardInput = source
    process.standardOutput = output
    process.standardError = FileHandle.nullDevice
    try process.run()
    try source.fileHandleForWriting.write(contentsOf: passphrase + Data([10]))
    try source.fileHandleForWriting.close()
    let plaintext = output.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()
    guard process.terminationStatus == 0 else { exit(1) }
    try FileHandle.standardOutput.write(contentsOf: plaintext)
} catch {
    // The parent must report generic failure and never display captured plaintext or Keychain errors.
    exit(1)
}

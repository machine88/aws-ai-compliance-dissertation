// Prepare one local evidence recipient. Private key stays encrypted; its random passphrase
// is stored only in a new dedicated macOS Keychain item. No AWS calls or secret logging.
// Inputs: one new local directory, macOS Keychain and the installed OpenSSL 3 binary.
// Outputs: encrypted key, public certificate, private metadata, one Keychain item and status-only stdout.
import Foundation
import Security
import CryptoKit
import Darwin

enum SetupFailure: Error { case stage(String) }

/// Run OpenSSL with sensitive input through an anonymous stdin pipe.
/// Inputs:
///   arguments: Public command options and file paths; never a passphrase.
///   input: In-memory stdin bytes; never written to a log or command line.
/// Outputs:
///   Data: Captured stdout in memory; nonzero status raises a stage-only failure.
func runOpenSSL(arguments: [String], input: Data) throws -> Data {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/opt/homebrew/opt/openssl@3/bin/openssl")
    process.arguments = arguments
    let source = Pipe(), output = Pipe()
    process.standardInput = source
    process.standardOutput = output
    process.standardError = FileHandle.nullDevice
    try process.run()
    try source.fileHandleForWriting.write(contentsOf: input)
    try source.fileHandleForWriting.close()
    let result = output.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()
    guard process.terminationStatus == 0 else { throw SetupFailure.stage("openssl") }
    return result
}

// Reserve a new private directory; never reuse a recipient or overwrite its key.
umask(0o077)
let arguments = CommandLine.arguments
guard arguments.count == 2 else { exit(2) }
let directory = URL(fileURLWithPath: arguments[1], isDirectory: true)
guard mkdir(directory.path, 0o700) == 0 else { exit(2) }
let service = "org.dissertation.evidence.recipient"
let account = UUID().uuidString
let key = directory.appendingPathComponent("private-key.encrypted.pem")
let certificate = directory.appendingPathComponent("recipient-public.pem")
let testCipher = directory.appendingPathComponent("recipient-self-test.cms")
let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                           kSecAttrService as String: service,
                           kSecAttrAccount as String: account]
var itemCreated = false

do {
    // Generate a high-entropy passphrase in memory, not in shell arguments or files.
    var random = [UInt8](repeating: 0, count: 32)
    let randomStatus = random.withUnsafeMutableBytes { SecRandomCopyBytes(kSecRandomDefault, $0.count, $0.baseAddress!) }
    guard randomStatus == errSecSuccess else { throw SetupFailure.stage("random") }
    let passphrase = Data(Data(random).base64EncodedString().utf8)
    var attributes = query
    attributes[kSecValueData as String] = passphrase
    attributes[kSecAttrLabel as String] = "Dissertation local evidence recipient"
    attributes[kSecAttrSynchronizable as String] = false
    guard SecItemAdd(attributes as CFDictionary, nil) == errSecSuccess else { throw SetupFailure.stage("keychain_add") }
    itemCreated = true
    var match = query
    match[kSecReturnData as String] = true
    match[kSecMatchLimit as String] = kSecMatchLimitOne
    var stored: CFTypeRef?
    guard SecItemCopyMatching(match as CFDictionary, &stored) == errSecSuccess,
          let storedData = stored as? Data, storedData == passphrase else { throw SetupFailure.stage("keychain_verify") }
    let input = passphrase + Data([10])
    // OpenSSL emits only an encrypted PKCS#8 private-key file; no plaintext key file is created.
    _ = try runOpenSSL(arguments: ["genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:3072", "-aes-256-cbc", "-pass", "stdin", "-out", key.path], input: input)
    _ = try runOpenSSL(arguments: ["req", "-new", "-x509", "-sha256", "-days", "365", "-key", key.path, "-passin", "stdin", "-out", certificate.path, "-subj", "/CN=Dissertation Local Evidence Recipient"], input: input)
    // Test the exact CMS encryption mode using a public dummy marker, never a real capture.
    let marker = Data("dissertation-recipient-self-test".utf8)
    let encrypted = try runOpenSSL(arguments: ["cms", "-encrypt", "-binary", "-aes-256-gcm", "-outform", "DER", "-recip", certificate.path, "-keyopt", "rsa_padding_mode:oaep", "-keyopt", "rsa_oaep_md:sha256"], input: marker)
    try encrypted.write(to: testCipher, options: .withoutOverwriting)
    let decrypted = try runOpenSSL(arguments: ["cms", "-decrypt", "-binary", "-inform", "DER", "-in", testCipher.path, "-recip", certificate.path, "-inkey", key.path, "-passin", "stdin"], input: input)
    guard decrypted == marker else { throw SetupFailure.stage("roundtrip") }
    try FileManager.default.removeItem(at: testCipher)
    let publicData = try Data(contentsOf: certificate)
    let pin = SHA256.hash(data: publicData).map { String(format: "%02x", $0) }.joined()
    let metadata: [String: Any] = ["status": "local_recipient_prepared", "certificate_file": certificate.lastPathComponent,
        "encrypted_private_key_file": key.lastPathComponent, "recipient_public_pem_sha256": pin,
        "keychain_service": service, "keychain_account": account, "keychain_sync": false,
        "key_type": "RSA-3072", "private_key_encrypted": true, "cms_roundtrip_passed": true]
    let encoded = try JSONSerialization.data(withJSONObject: metadata, options: [.prettyPrinted, .sortedKeys])
    try encoded.write(to: directory.appendingPathComponent("recipient-metadata.json"), options: .withoutOverwriting)
    print("{\"recipient_prepared\":true,\"private_key_encrypted\":true,\"keychain_verified\":true,\"roundtrip_passed\":true}")
} catch {
    // Clean up only the newly created dedicated item on failure; never touch existing user secrets.
    if itemCreated { SecItemDelete(query as CFDictionary) }
    print("{\"recipient_prepared\":false,\"error\":\"Local setup failed; partial files are not a usable recipient\"}")
    exit(1)
}

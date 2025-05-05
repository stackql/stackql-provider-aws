namespace smithy.test

use smithy.api#String

@trait
list smokeTests {
    member: SmokeTestCase
}

structure SmokeTestCase {
    operation: String
}

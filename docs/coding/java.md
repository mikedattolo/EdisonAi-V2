# Java Reference

General-purpose, statically-typed, compiled to JVM bytecode. Not used by Edison's own app, but supported for projects.

## Toolchain
- Check: `java -version`, `javac -version`. Install JDK on Ubuntu: `sudo apt install -y default-jdk` (or a specific one like `openjdk-21-jdk`).
- Compile + run (no build tool): `javac Main.java` → produces `Main.class` → `java Main`. With packages, compile from the source root and run the fully-qualified class.
- Modern single-file run (JDK 11+): `java Main.java` (compiles in memory).
- Build tools (preferred for real projects): Maven (`mvn package`, `mvn test`) or Gradle (`./gradlew build`, `./gradlew test`). See `dependency-management.md`.

## Core syntax
```java
public class Main {
  public static void main(String[] args) {
    int n = 5;                 // primitives: int long double boolean char byte short float
    String s = "hello";        // objects; String is immutable
    var list = new java.util.ArrayList<String>(); // var = inferred local type (Java 10+)
    list.add("a");
    for (String x : list) { System.out.println(x); }
    System.out.printf("%s = %d%n", s, n);
  }
}
```
- Types are explicit; every statement ends with `;`; blocks use `{}`. One public class per file, named like the file.
- Access: `public private protected`, `static`, `final` (constant/no-reassign). Packages: `package com.example;` + matching folders.

## OOP & generics
- Class with fields, constructor, methods: `class User { private final String name; User(String n){ this.name = n; } String name(){ return name; } }`.
- `interface Shape { double area(); }`; `class Circle implements Shape { ... }`; `extends` for inheritance; `@Override`.
- Generics: `List<String>`, `Map<String,Integer>`, `<T> T first(List<T> xs)`. Records (Java 16+): `record Point(int x, int y) {}`.
- Collections: `ArrayList`, `HashMap`, `HashSet`, `List.of(...)`, `Map.of(...)`. Streams: `list.stream().filter(x -> x>0).map(...).collect(Collectors.toList())`.

## Errors & resources
- `try { ... } catch (IOException e) { ... } finally { ... }`. Checked exceptions must be declared (`throws`) or caught.
- try-with-resources auto-closes: `try (var r = new BufferedReader(...)) { ... }`.
- Throw: `throw new IllegalArgumentException("msg");`.

## Idioms & gotchas
- Use `.equals()` for object/String comparison, not `==` (which compares references).
- Prefer `var` for obvious local types, interfaces for variable types (`List<X> xs = new ArrayList<>()`).
- Null handling: check or use `Optional<T>`. Prefer immutability (`final`, records).
- Entry point is exactly `public static void main(String[] args)`.

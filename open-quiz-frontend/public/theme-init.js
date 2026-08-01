;(function () {
    var theme = "system"

    try {
        var storedTheme = localStorage.getItem("vite-ui-theme")
        if (
            storedTheme === "dark" ||
            storedTheme === "light" ||
            storedTheme === "system"
        ) {
            theme = storedTheme
        }
    } catch {
        // Use the system preference when storage is unavailable.
    }

    var isDark =
        theme === "dark" ||
        (theme === "system" &&
            window.matchMedia("(prefers-color-scheme: dark)").matches)
    var root = document.documentElement

    root.classList.add(isDark ? "dark" : "light")
    root.style.colorScheme = isDark ? "dark" : "light"
    root.style.backgroundColor = isDark ? "#171717" : "#fbfaff"
})()

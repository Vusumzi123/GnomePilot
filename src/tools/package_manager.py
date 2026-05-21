"""Skill: Package management (search & install via pacman/AUR).

Register with `register(mcp)` -- called automatically by the plugin loader.
"""

import subprocess


def _search_packages(query: str) -> str:
    """Search pacman and AUR (via yay) for a package, returning top 5 from each."""
    results_parts = []
    pacman = subprocess.run(
        ["pacman", "-Ss", "--color", "never", query],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if pacman.returncode == 0 and pacman.stdout.strip():
        lines = pacman.stdout.strip().split("\n")
        official = [l for l in lines if not l.startswith(" ")]
        if official:
            results_parts.append("Official repositories:\n" + "\n".join(official[:5]))

    yay = subprocess.run(
        ["yay", "-Ss", "--color", "never", query],
        capture_output=True,
        text=True,
        timeout=60,
        env={**subprocess.os.environ, "YAY_ANSWER_ALL": "1"},
    )
    if yay.returncode == 0 and yay.stdout.strip():
        lines = yay.stdout.strip().split("\n")
        aur = [l for l in lines if "aur/" in l.lower()][:5]
        if aur:
            results_parts.append("AUR:\n" + "\n".join(aur))

    if not results_parts:
        return f"No packages found for '{query}'."
    return "\n\n".join(results_parts)


def _install_package(package_name: str) -> str:
    """Install a package via pkexec + pacman (requires user auth)."""
    result = subprocess.run(
        ["pkexec", "pacman", "-S", "--noconfirm", package_name],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode == 0:
        return f"Successfully installed {package_name}."
    return f"Failed to install {package_name}: {result.stderr.strip() or 'unknown error'}"


def register(mcp) -> None:
    @mcp.tool()
    def tool_search_packages(query: str) -> str:
        """Search for available software packages in pacman repositories and the AUR.

        Queries both official Arch repositories and the Arch User Repository (AUR)
        via yay. Returns top results from each.

        Args:
            query: Search term for the package (e.g. "web browser", "htop").
        """
        return _search_packages(query)

    @mcp.tool()
    def tool_install_package(package_name: str) -> str:
        """Install a software package using pacman (via pkexec for privileges).

        Use this after confirming the exact package name with search_packages.

        Args:
            package_name: Exact name of the package to install (e.g. "htop", "firefox").
        """
        return _install_package(package_name)

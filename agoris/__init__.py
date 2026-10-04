"""AGORIS - eine sichere Umgebung fuer unzuverlaessige KI-Agenten.

Der Kernsatz: **Was der Agent kann, entscheidet der Wirt, nicht der Agent.**

Ein Agent bekommt von AGORIS nur das, was die Policy erlaubt: Rechenzeit,
Speicher, Dateien, Netzwerkziele und Werkzeuge. Alles andere existiert fuer ihn
nicht - nicht "es wird spaeter blockiert", sondern gar nicht erst.

Schichten (Wirt / Gefaengnis):

* ``agoris.policy``   - was erlaubt ist (Wirt)
* ``agoris.limits``   - Ressourcengrenzen (Wirt)
* ``agoris.audit``    - manipulationssichere Protokollierung (Wirt)
* ``agoris.proxy``    - Richtlinien-Proxy fuer Netzzugriff (Wirt)
* ``agoris.model``    - Modell-Broker, haelt den API-Schluessel (Wirt)
* ``agoris.jail``     - Namespaces, chroot, Rechte, seccomp (Gefaengnis)
* ``agoris.runtime``  - der Agent-Loop und seine Werkzeuge (Gefaengnis)

Nur die Standardbibliothek, Python >= 3.8, keine externen Abhaengigkeiten.
"""

from .policy import Policy

__all__ = ["Policy", "__version__"]

__version__ = "0.1.0"
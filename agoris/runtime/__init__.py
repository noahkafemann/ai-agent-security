"""Der Teil von AGORIS, der *im Gefaengnis* laeuft.

``worker`` ist der Agent-Loop, ``tools`` sind die Werkzeuge, ``protocol`` ist der
einzige Kanal zum Wirt. Alles hier ist fuer den Agenten les- und ausfuehrbar -
deshalb ist es auch das, was ein Angreifer zuerst untersucht.
"""

from .protocol import Channel

__all__ = ["Channel"]
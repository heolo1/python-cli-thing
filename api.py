import menu
from typing import override

class API(menu.Command):
	def __init__(self):
		super().__init__("api")

menu.add_command(API())
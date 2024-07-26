# Todo

implement flag mappers!!

- i want it to be able to write something like "command blah -yM 1" and have it result in the python function call "command("blah", yellow=True, amount=1)"
  - this would require some kind of mapping ability like {"y": "yellow", "M": "amount"}
- to start, i should probably make something simpler, such as something that parses "command -yellow -amount" to "command(yellow=True, amount=True)"
  - this should probably also make a call like "command -yellow" run "command(yellow=True, amount=False)"
  - this can be done by reading the parameters of the function, finding the kw-only args, and just checking if it appeared in the list of flags or not
- of course, i have to find a good paradigm for creating flag mappers, since writing three nested functions is terrible
  - ill probably make some sort of base FlagMapper class and make a _cmd_deco_wrapper for adding it to a function
    - should i add it to register? maybe i will in the future

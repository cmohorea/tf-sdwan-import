import os

# target_fname = "sdwan-tf-import"

tf_header = \
"""
terraform {
  required_providers {
    sdwan = {
      source = "CiscoDevNet/sdwan"
      version = ">= 0.3.13"
    }
  }
}

variable "MANAGER_ADDR" { type = string }
variable "MANAGER_PASS" { type = string }
variable "MANAGER_USER" { type = string }

provider "sdwan" {
  url      = var.MANAGER_ADDR
  username = var.MANAGER_USER
  password = var.MANAGER_PASS
}

"""

# -------------------------------------------------------------------------------------
# Helper class
class text_handler:
    def __init__ (self, basename):
        self.texts = {}
        self.basename = basename

    def add (self, stream, line):

        # if stream does not exist, create it
        if stream not in self.texts.keys():
            with_header = stream == "main"
            fname = f"{self.basename}-{stream}.tf"
            self.texts[stream] = mytext (fname, with_header)

        self.texts[stream].add (line)

    def write (self):
        for stream in self.texts.keys():
            self.texts[stream].write()

# -------------------------------------------------------------------------------------
# Helper class
class mytext:
    def __init__ (self, filename="", with_header=False):
        self.filename = filename
        self.text = tf_header if with_header else ""

        # cleanup previous files so they don't mess up with TF
        if filename:
            try:
                os.remove(filename)
            except OSError:
                pass        

    def addraw (self, line):
        self.text = self.text + line

    def add (self, line):
        self.addraw (line + "\n")

    def write (self):
        if self.filename == "":
            self.print ()
        else:
            try:
                with open(self.filename, "w") as file:
                    file.write (self.text)
            except:
                raise SystemExit (f"Unable to write to the '{self.filename}' file, exiting...")
    
    def print (self):
        print (self.text)
    
# -------------------------------------------------------------------------------------
class all_id_class:
    def __init__ (self):
        self.dict = {}

    def add (self, id, name, type):
        self.dict[id] = {'name': name, 'type': type, 'seen': False }

    def get (self, id):
        item = self.dict.get (id,{})
        if item:
            self.dict[id]['seen'] = True
        return item

    def get_name (self, id):
        item = self.get (id)
        return item.get('name', id)

    def get_type (self, id):
        item = self.get (id)
        return item.get('type', id)

    def is_seen (self, id):
        item = self.dict.get (id,{})
        return item.get('seen', False)

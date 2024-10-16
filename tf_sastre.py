from tf_library import mytext,text_handler,all_id_class
import os, sys, json, re
import logging, argparse
from collections import OrderedDict

# working variables
target_fname = "sdwan-tf-import"
target_fname_tf = f"{target_fname}-config.tf"
target_fname_bash = f"{target_fname}.sh"

local_dir = "."
tfstate_file = "terraform.tfstate"

skip_defaults = True    # Skip default device templates

tf_type_device_template = "sdwan_feature_device_template"
tf_type_device_cli = "sdwan_cli_device_template"
tf_type_device_attach = "sdwan_attach_feature_device_template"

# -------------------------------------------------------------------------------------------------
def validate_content (name, id):
    return name and id

# -------------------------------------------------------------------------------------------------
def load_json_file (json_file):

    logging.debug (f"Processing template file {json_file}")

    if not re.match(r'.*\.json', json_file):
        logging.debug (f"Skipping {json_file}: not a .json file")
        return None

    try:
        with open(json_file, "r") as content_file:
            return json.load(content_file)
    except OSError as exception:
        logging.warning (f"Unable to read template file {json_file} ({exception})")
    except json.decoder.JSONDecodeError as exception:
        logging.warning (f"Unable to decode JSON in template file {json_file} ({exception})")

    return None

# -------------------------------------------------------------------------------------------------
# Translate SASTRE names to TF names
type_translate = {
    "config_groups": "configuration_group",
    "device_templates": "feature_device_template",                                         ## or cli_device_template, if CLI
    "feature_profiles_sdwan_cli": "cli_feature_profile",
    "feature_profiles_sdwan_application_priority": "application_priority_feature_profile",
    ## "feature_profiles_sdwan_embedded_security": "embedded_security_feature_profile",    ## ????
    ## "feature_profiles_sdwan_policy_object": "policy_object_feature_profile",            ## ????
    "feature_profiles_sdwan_service": "service_feature_profile",
    "feature_profiles_sdwan_system": "system_feature_profile",
    "feature_profiles_sdwan_transport": "transport_feature_profile",
    "feature_templates": "feature_template",
    "policy_definitions_acl": "ipv4_acl_policy_definition",
    "policy_definitions_approute": "application_aware_routing_policy_definition",
    "policy_definitions_cflowd": "cflowd_policy_definition",
    "policy_definitions_control": "custom_control_topology_policy_definition",
    "policy_definitions_data": "traffic_data_policy_definition",
    "policy_definitions_deviceaccess": "ipv4_device_acl_policy_definition",
    "policy_definitions_qosmap": "qos_map_policy_definition",
    "policy_definitions_rewriterule": "rewrite_rule_policy_definition",
    "policy_definitions_ruleset": "rule_set_policy_definition",
    "policy_definitions_securitygroup": "object_group_policy_definition",
    "policy_definitions_vedgeroute": "route_policy_definition",
    "policy_definitions_zonebasedfw": "zone_based_firewall_policy_definition",
    ## "policy_groups": "",
    "policy_lists_app": "application_list_policy_object",
    "policy_lists_appprobe": "app_probe_class_policy_object",
    "policy_lists_class": "class_map_policy_object",
    "policy_lists_color": "color_list_policy_object",
    "policy_lists_dataprefix": "data_ipv4_prefix_list_policy_object",
    "policy_lists_fqdn": "data_fqdn_prefix_list_policy_object",
    "policy_lists_localapp": "local_application_list_policy_object",
    "policy_lists_port": "port_list_policy_object",
    "policy_lists_preferredcolorgroup": "preferred_color_group_policy_object",
    "policy_lists_prefix": "ipv4_prefix_list_policy_object",
    "policy_lists_protocol": "protocol_list_policy_object",
    "policy_lists_site": "site_list_policy_object",
    "policy_lists_sla": "sla_class_policy_object",
    "policy_lists_tloc": "tloc_list_policy_object",
    "policy_lists_vpn": "vpn_list_policy_object",
    "policy_lists_zone": "zone_list_policy_object",
    "policy_templates_security": "security_policy",
    "policy_templates_customapp": "",   ####
    "policy_templates_vedge": "localized_policy",
    "policy_templates_vsmart": "centralized_policy",
}

template_type_fix = {
    "vpn_cedge_interface_cellular": "vpn_interface_cellular",
    "cellular_cedge_controller": "cellular_controller",
    "vpn_interface_ethpppoe": "vpn_interface_ethernet_pppoe",
}

def find_field_type (content, sastre_type):
    
    # Translate sastre types to TF types
    tf_type = type_translate.get(sastre_type, f"unknown type: {sastre_type}")
    
    # "device_template" covers both "feature_device_template" and "cli_device_template" types
    if tf_type == "feature_device_template" and content.get("configType", None) == "file":
        tf_type = "cli_device_template"

    if sastre_type == 'feature_templates':
        feature_template_type = content.get('templateType').replace("-","_")
        feature_template_type = template_type_fix.get (feature_template_type, feature_template_type)

        return f"{feature_template_type}_{tf_type}"
    else:
        return tf_type

# -------------------------------------------------------------------------------------------------
def find_field_by_name (content, field):
    """ Loose value find. E.g. Id, no matter what it is ("definitionId", "listId", "policyId", "profileId", "siteId", "templateId") 
        Hack: In config groups "Id" is called "id". And policy templates have "@rid" so cannot use lowercase
    """

    for key, value in content.items():
        # if re.search(field, key, re.IGNORECASE):
        
        if key == "id":
            key = "Id"
        if re.search(field, key):
            return (value)
    
    return "Not found"

# -------------------------------------------------------------------------------------------------
def is_vedge_device (content):

    vedges = ["vedge-1000","vedge-2000","vedge-cloud","vedge-5000","vedge-ISR1100-6G","vedge-100-B","vedge-ISR1100-4G","vedge-100","vsmart","vedge-ISR1100-4GLTE",
              "vedge-100-WM","vmanage","vedge-100-M","vedge-ISR1100X-6G","vedge-ISR1100X-4G", "vedge-cloud"]

    for vedge in vedges:
        if vedge in content.get ('deviceType',[]) or vedge in content.get ('device_type',[]):
            return True
    if content.get('templateType',"").find("vedge") >= 0:
        return True

# -------------------------------------------------------------------------------------------------
def is_unsupported_import_type (sastre_type):

    unsupported_sastre = ["feature_profiles_sdwan_embedded_security", "feature_profiles_sdwan_policy_object", "policy_groups", "policy_templates_customapp"]
    if sastre_type in unsupported_sastre:
        return True

# -------------------------------------------------------------------------------------------------
def skip_device_templates (object_type, object_name=""):

    skip_types = ["cli_device_template"]
    skip_templates = ['Default_', 'Factory_Default_']

    if object_type in skip_types:
        return True
    
    for skip_item in skip_templates:
        if re.match (skip_item, object_name):
            return True
    
# -------------------------------------------------------------------------------------------------
def is_unsupported_feature_template (content):

    unsupported = ["appqoe", "virtual-application-utd"]
    if content.get('templateType',"") in unsupported:
        return True

# -------------------------------------------------------------------------------------------------

def normalized_tf_resource_name (name):
    
    letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits  = "0123456789"

    valid_tf_first = "_" + letters
    valid_tf_chars = "_-" + letters + digits
    
    if name[0] not in valid_tf_first:
        name = '_' + name 
    
    name1 = ""
    for c in name:
        if c in valid_tf_chars:
            name1 += c
        else:
            name1 += "_"
    name = name1
    
    return name

# -------------------------------------------------------------------------------------------------
def load_json_directory (json_directory, destination_dir):

    text_tf   = mytext(f"{destination_dir}{target_fname_tf}", True) # first TF skeleton
    text_bash = mytext(f"{destination_dir}{target_fname_bash}")     # bash import script
    text_bash.add ("#!/bin/bash\n")  

    json_files = next(os.walk(json_directory), (None, None, []))[2]
    for json_file in json_files:
        
        full_content = load_json_file (f"{json_directory}/{json_file}")
        if full_content:
            sastre_type = json_file.split(".")[0]
            for content in full_content:
                object_tf_type = find_field_type (content, sastre_type)
                # TF rules: A name must start with a letter or underscore and may contain only letters, digits, underscores, and dashes.
                # prepend with _ if starts with - or digit
                object_name = normalized_tf_resource_name (find_field_by_name (content, r'ame$'))
                object_id = find_field_by_name (content, r'Id$')
                
                # Safety check
                if not validate_content (object_name, object_id):
                    logging.warning (f"'{json_file}' does not seem to contain SD-WAN JSON details, skipping...")
                    continue

                if is_unsupported_import_type(sastre_type):
                    logging.debug (f"Skipping '{object_name}' due to '{sastre_type}' type not supported")
                    continue

                if sastre_type == "device_templates" and skip_defaults and skip_device_templates (object_tf_type, object_name):
                    logging.debug (f"Skipping device template '{object_name}' due to explicit skip")
                    continue

                if sastre_type == "feature_templates" and is_vedge_device (content):
                    logging.debug (f"Skipping feature template '{object_name}' due to no support for vedge devices")
                    continue

                if sastre_type == "feature_templates" and is_unsupported_feature_template (content):
                    logging.debug (f"Skipping feature template '{object_name}' due to not supported by the current TF provider")
                    continue

                logging.debug (f"Adding '{sastre_type}' object '{object_name}'")
                # logging.debug (f'resource "sdwan_{object_tf_type}" "{object_name}" {{\n}}')
                # logging.debug (f'terraform import sdwan_{object_tf_type}.{object_name} {object_id}')
                text_tf.add (f'resource "sdwan_{object_tf_type}" "{object_name}" {{\n}}')
                text_bash.add (f'terraform import sdwan_{object_tf_type}.{object_name} {object_id}')

    text_bash.write()
    text_tf.write()

# -------------------------------------------------------------------------------------------------
def terraform_import (source_dir, destination_dir, use_api):

    # Process vManage API data
    load_json_directory (source_dir + "/inventory", destination_dir)

    # Init TF: clean up old tfstate and initialize provider
    os.system(f"mv {local_dir}/terraform.tfstate {local_dir}/terraform.tfstate.~~~bck 2>/dev/null")
    
    # This is needed in case provider is not activated, or is outdated
    tf_init_result = os.system(f"terraform init -upgrade")
    if tf_init_result != 0:
        logging.error (f'Terraform init failure: {tf_init_result}, exiting...')
        exit (1)

    # Execute import script and populate tfstate with live data
    os.system(f"chmod +x {target_fname_bash}")
    result = os.system(f"{local_dir}/{target_fname_bash}")
    if result != 0:
        logging.error (f'Error executing terraform import script, exiting...')
        exit (1)

    # os.system(f"rm {destination_dir}{target_fname_tf}")

# ************************************************************************************************* #
#                                 Processing tfstate file                                           #
# ************************************************************************************************* #
# -------------------------------------------------------------------------------------------------
def load_tf_file (tf_file):
    try:
        with open(tf_file, "r") as content_file:
            return json.load(content_file)
    except OSError as exception:
        print (f"Unable to read device template {tf_file} ({exception})")
    except json.decoder.JSONDecodeError as exception:
        print (f"Unable to decode JSON in device template {tf_file} ({exception})")
    except:
        return None

# -------------------------------------------------------------------------------------------------
def get_stream (tf_type):

    words = tf_type.split("_")
    if len (words) > 1:
        return f'{words[-2]}_{words[-1]}'
    else:
        return tf_type

# # -------------------------------------------------------------------------------------------------
# def key_norm (key):
#     return key.replace ('"', '').lstrip()

# -------------------------------------------------------------------------------------------------
def SortFunction (item):
    
    sort_seq = ["id", "name", "description", "device_types", "vpn_id", "interface_name", "interface_description", "address_variable", "dhcp", 
                "match_entries", "action_entries"]
    
    try:
        idx = str(sort_seq.index (item)+1000)
    except:
        idx = "9999"
    return idx + item


# -------------------------------------------------------------------------------------------------
def id_to_name (line):
    # input: any TF line with id
    # return: id is replace with the name, if it's known

    pattern_for_object_id = '(.*)(\w{8}-\w{4}-\w{4}-\w{4}-\w{12})(.*)'

    result = re.match(pattern_for_object_id, line)
    if result:
        indent = result.group(1)
        value = result.group(2)
        tail = result.group(3)
        name = all_IDs.get_name (value) 
        line = indent + name + tail

    return line

# -------------------------------------------------------------------------------------------------
def parse_tf_line (tf_line):
    # input: TF line e.g. 
    #       "policy_id": "693db1a3-9f6f-49a2-8c72-76bca3495bb5",
    #                "id": "26c78907-6d10-4dc3-8b47-b58197b7725a",
    # return:
    #       indent, key, value, name: ['    ', 'id', '693db1a3-9f6f-49a2-8c72-76bca3495bb5', 'SITE_BFD'/693db1a3-9f6f-49a2-8c72-76bca3495bb5]

    pattern_for_key_object  = '( *)"(.*)": *"(.*)"(.*)'  # "id": "26c78907-6d10-4dc3-8b47-b58197b7725a",
    pattern_for_object_id = '\w{8}-\w{4}-\w{4}-\w{4}-\w{12}'
    pattern_for_key = '( *)"(.*)": (.*)'      # "id": [

    result = re.match(pattern_for_key_object,  tf_line)
    if result:
        indent = result.group(1)
        key = result.group(2)
        value = result.group(3)
        # is_id = re.match (pattern_for_object_id, value)
        # name = all_IDs.get_name (value) if is_id else value
        name = id_to_name (value)
        # tail = result.group(3)
        return [indent, key, value, name]

    result = re.match(pattern_for_key,  tf_line)
    if result:
        indent = result.group(1)
        key = result.group(2)
        value = result.group(3)
        return [indent, key, value]

    tf_line = id_to_name (tf_line)

    return [tf_line]

# -------------------------------------------------------------------------------------------------
def tfstate_process_list (text, res_type):
    """ process top level multiline list elements """

    out = mytext()
    lines = text.split("\n")
    for line in lines:
        if ": null" in line:
            continue
        # hacking for device templates, replace ID with TF obj reference
        # "id": "1039812038" -> "id" = sdwan_cedge_aaa_feature_template.Global_AAA.id,
        pline = parse_tf_line (line)
        if len (pline) == 4:
            [ indent, key, value, name ] = pline
            # if res_type == tf_type_device_template and key == 'id' and name != value:  
            if res_type == tf_type_device_template and name != value:  
                out.add (f'  {indent}{key} = {name}.id,')
                out.add (f'  {indent}version = {name}.version,')
            elif name != value:  # replace id with the name
                out.add (f'  {indent}{key} = {name},')
            else:
                out.add (f'  {indent}{key} = "{name}",')
        elif len (pline) == 3:
            [ indent, key, value ] = pline
            out.add (f'  {indent}{key} = {value}')
        else:  
            out.add (f'  {pline[0]}')

    return out.text.rstrip("\n")

# -------------------------------------------------------------------------------------------------
def process_tfstate_file (resources, texts):
    """ go through the tfstate file and extract non-default values """

    commented = ["id"]
    skipped = [None, "template_type"]

    for resource in resources:
        resource_type = resource["type"]
        stream = get_stream (resource_type)

        texts.add (stream, f'resource \"{resource_type}\" \"{resource["name"]}\" {{')

        for item in resource["instances"]:

            keylist = list(item["attributes"].keys())
            keylist.sort (key = SortFunction)
            for key in keylist:
                value = item["attributes"][key]
                
                if value in skipped or key in skipped:
                    continue

                # comment = "# " if key in commented else ""
                if key == "id":
                    key = "# " + key

                # json formats to TF formats
                if type (value) == bool:
                    value = str (value).lower()
                # if type (value) == int:
                #     value = str (value)

                if type (value) == str:
                    value = value.replace("\n","\\n")   # CLI templates come with "\n" or "\r\n"
                    value = value.replace("\r","")
                    # value = value.replace("\\","\\\\")  # escape backslash
                    value = f'"{all_IDs.get_name (value)}"' 
                if type (value) == list:
                    # simple list - keep 1 liner
                    if type (value[0]) == str:
                        value = str(value)
                    # complex structure - process line by line
                    else:
                        # keylist = value.keys()
                        # keylist.sort (key = SortFunction)
                        # sorted_value = {key:value[key] for key in value.keys()}
                        value = tfstate_process_list (json.dumps(value, indent=2), resource_type)

                    value = value.replace("'",'"').lstrip()
                
                texts.add (stream, f"  {key} = {value}")
        texts.add (stream, "}\n")

# -------------------------------------------------------------------------------------------------
def terraform_create (source_dir, destination_dir):

    global all_IDs

    all_IDs = all_id_class()

    tfstate = load_tf_file (f"{source_dir}{tfstate_file}")
    if not tfstate:
        raise SystemExit (f"Cannot load {tfstate_file} file")

    # Create ID -> Name map 
    for resource in tfstate["resources"]:
        # safety precaution
        if len (resource["instances"]) > 1:
            logging.critical (f"Resource {resource.get('name')} has more than 1 instance, please check")
            exit(1)
        # still looping over
        for item in resource["instances"]:
            id = item["attributes"].get('id')
            name = normalized_tf_resource_name (item["attributes"].get('name'))
            type = resource.get('type',"UNKNOWN TYPE")
            all_IDs.add (id, f"{type}.{name}", type)

    # device templates need to be processed first so we know which feature templates are in use
    tf_state_devices = []
    tf_state_rest = []
    for resource in tfstate["resources"]:
        if resource.get('type') in [tf_type_device_template, "sdwan_application_aware_routing_policy_definition"]:
            if is_vedge_device (resource.get('instances',[[]])[0].get('attributes',{})):
                continue
            tf_state_devices.append (resource)
        elif resource.get('type') == tf_type_device_cli:
            continue
        else:
            tf_state_rest.append (resource)

    texts = text_handler(f"{destination_dir}{target_fname}")
    texts.add ("main", "")

    # texts.add ("main", "test1")
    # texts.add ("device", "test1")
    # texts.add ("template", "test1")
    # texts.write()

    process_tfstate_file (tf_state_devices, texts)
    process_tfstate_file (tf_state_rest, texts)

    texts.write()


# ************************************************************************************************* #
#                                 Processing device variables                                       #
# ************************************************************************************************* #
# -------------------------------------------------------------------------------------------------
def get_var_name (field):
    """ Extract var name from long GUI name """

    # Use value in brackets or just return a full original name
    result = re.search(r"\((.*)\)$", field)
    value = result.group(1) if result else field

    #add quotes if unsupported characters in var name...
    if " " in value or "/" in value:
        value = '"' + value + '"'

    return value

def terraform_variables (source_dir, destination_dir, use_api):

    json_directory = source_dir + "/device_templates/values"
    var_stream = "variables"

    texts = text_handler(f"{destination_dir}{target_fname}")
    device_variables = {}

    # if using sastre
    json_files = next(os.walk(json_directory), (None, None, []))[2]
    for json_file in json_files:
        content = load_json_file (f"{json_directory}/{json_file}")
        if content:
            template_name = json_file.split(".")[0]
            device_variables[template_name] = content
    # if using API...

    # start processing
    
    for template_name, variables in device_variables.items():
        var_index = {}
        for col in variables["header"]["columns"]:
            var_index[col["property"]] = get_var_name(col["title"])

        template_name = normalized_tf_resource_name (template_name)
        texts.add (var_stream, f'resource "sdwan_attach_feature_device_template" "{template_name}" {{')
        texts.add (var_stream, f'  id = sdwan_feature_device_template.{template_name}.id')
        texts.add (var_stream, f'  version = sdwan_feature_device_template.{template_name}.version')
        texts.add (var_stream, f'  devices = [')

        for device_var in variables['data']:
            device_id = device_var.get ("csv-deviceId")
            texts.add (var_stream,  '    {')
            texts.add (var_stream, f'      id = "{device_id}"')
            texts.add (var_stream,  '      variables = {')
            for key in sorted(device_var.keys()):
                if key[:4] != "csv-":   # ignore csv-... values
                    texts.add (var_stream, f'        {var_index[key]} = "{device_var[key]}"')

            texts.add (var_stream,  '      },')
            texts.add (var_stream,  '    },')
        texts.add (var_stream,  '  ]')
        texts.add (var_stream,  '}')

    texts.write()

# ==============================================================================================
def main():
    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)

    parser = argparse.ArgumentParser(description="Import SD-WAN configuration into Terraform")

    # parser.add_argument('action', choices=['import', 'create', ''], help='Action to perform')
    # parser.add_argument('-a', '--amend', action='store_true', help='Amend existing configuration using partial config')
    # parser.add_argument('-p', '--push', action='store_true', help='Push updated configuration to WAN edge devices')


    subparsers = parser.add_subparsers(dest='action', help = "Action to perform")
    import_parser = subparsers.add_parser('import', help = "Process SD-WAN data and import from Terraform into terraform.tfstate")
    import_parser.add_argument('-a', '--api', action='store_true', help="Do live API calls instead of using sastre backup")
    import_parser.add_argument('-s', '--source_dir', default = "./data", help="Directory with the sastre backup files")
    import_parser.add_argument('-d', '--destination_dir', default = "./", help="Directory to store Terraform.tfstate file")

    create_parser = subparsers.add_parser('create', help="Process previously created terraform.tfstate and create Terraform resources")
    create_parser.add_argument('-s', '--source_dir', default = "./", help="Directory with the source terraform.tfstate file")
    create_parser.add_argument('-d', '--destination_dir', default = "./", help="Directory to store target Terraform configuration files")

    vars_parser = subparsers.add_parser('vars', help="Process SD-WAN data and create Terraform device variables resources")
    vars_parser.add_argument('-a', '--api', action='store_true', help="Do live API calls instead of using sastre backup")
    vars_parser.add_argument('-s', '--source_dir', default = "./data", help="Directory with the sastre backup files")
    vars_parser.add_argument('-d', '--destination_dir', default = "./", help="Directory to store target Terraform configuration file")

    args = parser.parse_args(None if sys.argv[1:] else ['-h'])

    action = args.action

    source_dir = "./" if args.source_dir == "" else args.source_dir
    if source_dir [-1] != '/':
        source_dir += '/'

    destination_dir = "./" if args.destination_dir == "" else args.destination_dir
    if destination_dir [-1] != '/':
        destination_dir += '/'


    if action == "import":
        print ("Doing import")
        terraform_import (source_dir, destination_dir, args.api)
    elif action == "create":
        print ("Doing create")
        terraform_create (source_dir, destination_dir)
    elif action == "vars":
        print ("Doing vars")
        terraform_variables (source_dir, destination_dir, args.api)
    else:
        print ("Should not be here!")

if __name__ == '__main__':
    main()

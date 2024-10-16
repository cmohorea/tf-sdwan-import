import json
from tf_library import mytext, target_fname

# LAB1-DC-HUB - 3 devices
# LAB1_SITE7_LARGE_SITE_ADJACENT, LAB1_SITE6a_WAYSIDE_TFS - 2
# LAB1_SITE2_MEDIUM_SITE_MT_R1 - 1

source_filename = "sdwan.json"

# input parameters
# target_fname = "sdwan-tf-import"
target_device_templates = ['LAB1-DC-HUB', 'LAB1_SITE7_LARGE_SITE_ADJACENT', 'LAB1_SITE6a_WAYSIDE_TFS', 'LAB1_SITE2_MEDIUM_SITE_MT_R1']
tfstate_file = "terraform.tfstate"

# working variables
target_fname_main = f"{target_fname}-config.tf"
target_fname_import = f"{target_fname}.sh"

# TF provider bug
feature_template_type_fix = {
    "vpn_cedge_interface_cellular": "vpn_interface_cellular"
}

# ----------------------------------------------------------------------------------------
def find_device_template (device_template_name):
    """ in: template name; out: template structure """

    for device_template in alldata['feature_device_template']:
        if device_template['data']['templateName'] == device_template_name:
            return device_template['data']
        
    return None

# ----------------------------------------------------------------------------------------
def find_feature_template (feature_template_id):
    """ in: template id; out: template structure """

    for feature_template in alldata['feature_templates']:
        # print (f">>> {feature_template['data']['templateId']} vs. {feature_template_id}")
        if feature_template['data']['templateId'] == feature_template_id:
            return feature_template['data']
        
    return None

# ----------------------------------------------------------------------------------------
def find_data_policy (policy_id):
    """ in: policy id; out: template structure """

    for data_policy in alldata['localized_policy']:
        if data_policy['data']['policyId'] == policy_id:
            return data_policy['data']
        
    return None

# ----------------------------------------------------------------------------------------
def find_config_item (id_name, id):
    """ General search across whole config """

    for tld in alldata.keys():
        for sld in alldata[tld]:
            if sld.get('data',"").get(id_name) == id:
                return [tld, sld['data']]
    
    return [None, None]

# ----------------------------------------------------------------------------------------
def process_feature_template (feature_template):

    feature_template_id = feature_template.get('templateId',"")
    # avoid duplicates
    if feature_template_id in seen_IDs:
        return 
    
    feature_template = find_feature_template (feature_template_id)
    feature_template_name = feature_template.get ('templateName',"UNKNOWN")
    feature_template_type = feature_template.get('templateType',"").replace("-","_")
    if feature_template_type in feature_template_type_fix.keys():
         feature_template_type = feature_template_type_fix[feature_template_type]

    text_tf.add (f'resource "sdwan_{feature_template_type}_feature_template" "{feature_template_name}" {{\n}}')
    text_bash.add (f'terraform import sdwan_{feature_template_type}_feature_template.{feature_template_name} {feature_template_id}')
    seen_IDs.add(feature_template_id)

# ----------------------------------------------------------------------------------------
def process_data_policy (data_policy_id):

    # policy_types = ['qosMap', 'rewriteRule', 'vedgeRoute', 'acl', 'aclv6', 'deviceAccessPolicy', 'deviceAccessPolicyv6']

    if data_policy_id in seen_IDs:
        return 
    
    data_policy = find_data_policy (data_policy_id)
    data_policy_name = data_policy.get('policyName',"ERROR")

    text_tf.add (f'resource "sdwan_localized_policy" "{data_policy_name}" {{\n}}')
    text_bash.add (f'terraform import sdwan_localized_policy.{data_policy_name} {data_policy_id}')

    policy_definition = json.loads(data_policy['policyDefinition'])
    for item in policy_definition.get('assembly'):
        if item['definitionId'] in seen_IDs:
            continue 
        [tf_name, policy] = find_config_item ('definitionId', item['definitionId'])
        if tf_name:
            if policy['type'] != item['type']:
                print ("Found something strange!..")
            # print (f" sdwan_{tf_name} {policy['name']} - {policy['definitionId']}")
            text_tf.add (f'resource "sdwan_{tf_name}" "{policy["name"]}" {{\n}}')
            text_bash.add (f'terraform import sdwan_{tf_name}.{policy["name"]} {policy["definitionId"]}')
            seen_IDs.add (policy["definitionId"])

    seen_IDs.add (data_policy_id)

# ----------------------------------------------------------------------------------------
def process_device_template (device_template):

    template_id = device_template.get ("templateId","ERROR")
    template_name = device_template.get ("templateName","ERROR")

    text_tf.add (f'resource "sdwan_feature_device_template" "{template_name}" {{\n}}')
    text_bash.add (f'terraform import sdwan_feature_device_template.{template_name} {template_id}')

    print (f"Processing {template_name} device template")
    for feature_template in device_template.get('generalTemplates',[]):
        # print (f'{feature_template.get("templateId")} ({feature_template.get("templateType")})')
        process_feature_template (feature_template)
        sub_feature_templates = feature_template.get('subTemplates')
        if sub_feature_templates:
            for sub_feature_template in sub_feature_templates:
                process_feature_template (sub_feature_template)

    data_policy_id = device_template.get ("policyId", None)
    if data_policy_id:
        process_data_policy (data_policy_id)
    # "securityPolicyId"

    return 

# # ------------------------------ start of the script ------------------------------------------
# ========================================= start ========================================
# ============ Step 1: Init
with open(source_filename) as json_data:
    alldata = json.load (json_data)

# init text structures
text_tf   = mytext(target_fname_main, True) # first TF skeleton
text_bash = mytext(target_fname_import)     # bash import script
text_bash.add ("#!/bin/bash\n")  
# text_main    = mytext(target_fname_main, True)            # final TF file: feature templates
# text_device  = mytext(target_fname_device)                     # final TF file: device templates
# text_attach  = mytext(target_fname_attach)                     # final TF file: "attach" resources

# ============ Step 2: process requested device templates

seen_IDs = set()

for device_template_name in target_device_templates:
    device_template = find_device_template (device_template_name)

    if device_template:
        process_device_template (device_template)
    else:
        print (f"Device template {device_template_name} not found. The following device templates are available:")
        for device_template in alldata['feature_device_template']:
            print (f"- {device_template['data']['templateName']}")
        raise SystemExit ("Exiting...")

# for device_template in alldata['feature_device_template']:
#     if device_template['data']['templateName'] in target_device_templates:
#         process_device_template (device_template['data'])
#     else:
#         print (f"Device template {device_template} not found. The following device templates are available:")
#         for device_template in alldata['feature_device_template']:
#             print (f"- {device_template['data']['templateName']}")
#         raise SystemExit ("Exiting...")
    # for j in v:
    #     print (j['data']['templateName'])

text_bash.write()
text_tf.write()

# print ("*"*80)
# text_bash.print()
# print ("*"*80)
# text_tf.print()
# print ("*"*80)

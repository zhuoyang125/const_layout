import networkx as nx
import requests
import matplotlib.pyplot as plt
from PIL import Image
import json
import boto3
from botocore.exceptions import ClientError
import logging

GENERATION_ENDPOINT = 'https://infographic-generator-106858723129.herokuapp.com'

def convert_plt_to_img(fig):
    """Convert a Matplotlib figure to a PIL Image and return it"""
    import io
    buf = io.BytesIO()
    fig.savefig(buf)
    buf.seek(0)
    img = Image.open(buf)
    return img

def convert_graph_to_image(adj_list, node_occurences, entity_labels):
    # create the graph
    DG = nx.DiGraph()
    # add nodes
    for i in range(len(node_occurences)):
        DG.add_node(i)
    
    # add edges
    for n in adj_list:
        for nbr in adj_list[n]:
            DG.add_edge(n, nbr)
    
    nx.draw_networkx(DG, with_labels=True, labels=entity_labels, node_size=node_occurences)
    fig = plt.gcf()
    img = convert_plt_to_img(fig)
    return img

def event_to_dict(event):
    '''
    creates and returns a dict containing all event information.
    '''
    return {
        'request_id': event.request_id,
        'title': event.title,
        'description': event.description,
        'related_articles': event.related_articles,
        'image': event.image,
        'adj_list': event.adjList,
        'node_occurences': event.node_occurences,
        'entity_labels': event.entity_labels
    }

# Querying infographic generator endpoint
def get_generation_from_api(num_label, label):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    res = requests.post(url=GENERATION_ENDPOINT + '/generate', data=json.dumps({'num_label': num_label, 'label': label}), headers=headers, timeout=60)
    bboxes, labels = res.json()['results']['bbox'], res.json()['results']['label']
    return bboxes, labels

def get_edit_from_api(id_a, id_b, relation, bbox, num_label, label):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    res = requests.post(url=GENERATION_ENDPOINT + '/generate', data=json.dumps({'id_a': id_a, 'id_b': id_b, 'relation': relation, 'bbox': bbox, 'num_label': num_label, 'label': label}), headers=headers, timeout=60)
    bboxes, labels = res.json()['results']['bbox'], res.json()['results']['label']
    return bboxes, labels

def convert_layout_to_infographic(input_dict, boxes, labels, canvas_size): 
    '''
    the input is a dict[label_index: [values of each label element]]
    e.g. {0: ['Biden', 'Trump']}
    images are represented by Pillow Image object.
    '''
    H, W = canvas_size
    img = Image.new('RGB', (int(W), int(H)), color=(255,255,255))
    draw = ImageDraw.Draw(img, 'RGBA')

    area = [b[2] * b[3] for b in boxes]
    indices = sorted(range(len(area)), key=lambda i:area[i], reverse=True)

    for i in indices:
        bbox, label = boxes[i], labels[i]
        x1, y1, x2, y2 = convert_xywh_to_ltrb(bbox)
        x1, y1, x2, y2 = int(x1*W), int(y1*H), int(x2*W), int(y2*H)

        if label == 1 or label == 2:
            img_to_paste = input_dict[label][0].resize((x2-x1, y2-y1))
            img.paste(img_to_paste, (x1, y1, x2, y2))
            input_dict[label].pop(0)
        else:
            # text
            text = input_dict[label][0]
            font_size = 100
            words = text.split()
            
            while font_size > 0:
                size = None
                curr_words = []
                idx = 0 # index of current word to select
                while idx < len(words):
                    l, t, r, b = draw.multiline_textbbox((x1, y1), ' '.join(curr_words), font_size=font_size)
                    size = (r-l, b-t) # (width, height)
                    if size[1] > y2-y1:
                        break
                    if size[0] < x2-x1:
                        curr_words.append(words[idx])
                        idx += 1
                    else:
                        if curr_words[-1] == '\n':
                            break
                        curr_words.pop()
                        idx -= 1
                        curr_words.append('\n') # add new line  

                if idx >= len(words):
                    break
                font_size -= 1
            draw.multiline_text((x1, y1), ' '.join(curr_words), fill="#000", font_size=font_size)
    return img

# AWS Operations
def upload_fileobj(file_object, bucket, object_name):
    """Upload a file to an S3 bucket

    :param file_obj: File object to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # Upload the file
    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_fileobj(file_object, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True

def download_fileobj(bucket, object_name, file_object):
    """
    Download a file from S3 bucket

    :param file_name: file name to download
    :param bucket: bucket to download from
    :param object_name S3 object name
    :return True if file was succesfully downloaded, else False
    """
    s3_client = boto3.client('s3')
    try:
        response = s3_client.download_fileobj(bucket, object_name, file_object)
    except ClientError as e:
        logging.error(e)
        return False
    return True

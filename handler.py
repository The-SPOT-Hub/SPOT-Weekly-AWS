from slack import posts_all_courses

def lambda_handler(event, context):
    posts_all_courses()
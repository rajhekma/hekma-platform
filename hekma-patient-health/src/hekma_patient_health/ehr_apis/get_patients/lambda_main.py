#from hekma_data_pipleline.awsutils.elasticsearch_utils import ElasticSearchConnection
# from ...awsutils.postgresql_utils import (
#     get_pg_connection,
#     release_pg_connection
# )
from ...awsutils.postgresql_utils import pg_transaction

def get_details(
    start: int = 0,
    size: int = 100,
    patient_ids: list = None,
    hekma_mail: str = None,
    text_search: str = None
):
    with pg_transaction(dict_cursor=False) as (conn, cursor):

        where_sql = ""
        params = []

        # CASE A: patient_ids only (email is never a chart key)
        if patient_ids:
            where_sql = """
                WHERE id = ANY(%s)
                  AND archived_at IS NULL
            """
            params = [patient_ids]

        # CASE B: living email fallback — resolve one id at the API layer.
        # This path keeps empty results if the caller still passes mail only.
        elif hekma_mail:
            where_sql = """
                WHERE id = %s
                  AND archived_at IS NULL
            """
            from ...ehr_apis.ctms_patient_ids import resolve_living_patient_by_email

            living_id = resolve_living_patient_by_email(hekma_mail)
            if not living_id:
                where_sql = "WHERE FALSE"
                params = []
            else:
                params = [living_id]

        # CASE D: text_search
        elif text_search:
            text_list = text_search.split(" ")
            where_sql = """
                WHERE (
                    family_name = ANY(%s)
                    OR given_name = ANY(%s)
                )
                  AND archived_at IS NULL
            """
            params = [text_list, text_list]

        # total count
        cursor.execute(
            f"SELECT COUNT(*) FROM patient {where_sql}",
            params
        )
        total = cursor.fetchone()[0]

        # main query
        cursor.execute(
            f"""
            SELECT raw_resource
            FROM patient
            {where_sql}
            ORDER BY given_name ASC
            OFFSET %s
            LIMIT %s
            """,
            params + [start, size]
        )

        rows = cursor.fetchall()

        data = {
            "total": total,
            "data": [],
            "from": start,
            "size": 0
        }

        for (raw_resource,) in rows:
            source = raw_resource
            if "name" in source:
                try:
                    if isinstance(source["name"][0].get("family"), str):
                        name = source["name"][0]
                        name["family"] = [name["family"]]
                        source["name"] = [name]
                except Exception:
                    pass
            data["data"].append(source)

        data["size"] = len(data["data"])
        return data



# def get_details(start: int = 0, size: int = 100, patient_ids: list = None, hekma_mail: str = None,
#                 text_search: str = None):
#     param = {'from_': start, 'size': size}
#     es = ElasticSearchConnection()
#     body = {
#         "sort": {
#             "name.given.keyword": {"order": "asc"}
#         }
#     }
#     if patient_ids and hekma_mail:
#         should = list()
#         should.append({
#              "terms": {
#                 "id.keyword": patient_ids
#             }
#         }
#         )
#         should.append({
#              "match": {
#                 "hekma_mail.keyword": hekma_mail
#             }
#         }
#         )
#         body['query'] = {
#             "bool": {
#                 "should": should
#             }
#         }
#     elif patient_ids:
#         body["query"] = {
#             "terms": {
#                 "id.keyword": patient_ids
#             }
#         }
#     elif hekma_mail:
#         body["query"] = {
#             "match": {
#                 "hekma_mail.keyword": hekma_mail
#             }
#         }
#     elif text_search:
#         text_list = text_search.split(" ")
#         should = list()
#         should.append({
#             "terms": {
#               "name.family.keyword": text_list
#             }
#           }
#         )
#         should.append({
#             "terms": {
#                 "name.given.keyword": text_list
#             }
#         }
#         )
#         body['query'] = {
#             "bool": {
#                 "should": should
#             }
#         }
#     print(body)
#     response = es.search(index='patient', body=body, param=param)
#     data = dict()

#     data['total'] = response['hits']['total']['value']
#     data['data'] = []
#     data['from'] = start
#     for d in response['hits']['hits']:
#         source = d['_source']
#         if 'name' in source:
#             try:
#                 if isinstance(source['name'][0]['family'], str):
#                     new_name = list()
#                     name = source['name'][0]
#                     name['family'] = [name['family']]
#                     new_name.append(name)
#                     source['name']=new_name
#             except:
#                 q=1 # Do nothing

#         data['data'].append(source)
#     data['size'] = len(data['data'])

#     return data


def patients_get_handler(event, context):

    if isinstance(event, dict) and "params" in event and "querystring" in event["params"]:
        event = event["params"]["querystring"]

    start = 0
    if 'from' in event:
        start = int(event['from'])

    size = 100
    if 'size' in event:
        size = int(event['size'])

    patient_ids = None
    hekma_mail = None
    test_search1 = None

    if 'ids' in event:
        print(event['ids'])
        patient_ids = event['ids'].split(",")

    if 'hekmaMail' in event:
        hekma_mail = event['hekmaMail']

    if 'text_search' in event:
        test_search1 = event['text_search']

    return get_details(
        start=start,
        size=size,
        patient_ids=patient_ids,
        hekma_mail=hekma_mail,
        text_search=test_search1
    )



if __name__ == '__main__':

    exit()
    import re
    a = "9"

    print(a.isupper())
    print(a.islower())
    print(a.isdigit())
    exit()

    x = ['ab', 'cd']
    print(list(map(len(x), x)))
    exit()
    data = [1, 2, 3]

    #d = copy(data)
    data.copy()
    print(list(data))

    def incr(x):
        return x + 1


    print(list(map(incr, data)))

    exit()
    print("Welcome to TURING".capitalize())
    exit()
    try:
        i=9
    except:
        i=9
    finally:
        i=9
    exit()
    class Welcome:

        def __init__(self, name):
            self.name = name

        def say_hello(self):
            print('Welcome to ', self.name)


    cw = Welcome('Turing')
    cw.say_hello()
    exit()
    def f(x, l=[]):
        for i in range(x):
            l.append(i * i)
        print(l)


    f(2)
    f(3, [3, 2, 1])
    f(3)
    exit()
    Y = [2, 5J, 6]
    Y.sort()
    print(Y)
    exit()
    inputs = ['nodejs', 'reactjs', 'vuejs']
    print(inputs)

    for i in inputs:
        inputs.append(i.upper())

    print(inputs)
    exit()
    l = [1, 2, 3, 4, 5]
    m = map(lambda x: 2 ** x, l)
    print(list(m))
    exit()
    a = [1, 2, 3, 4]
    b = [sum(a[0:x + 1]) for x in range(0, len(a))]
    print(b)
    exit()
    print(2 ** (3 ** 2), (2 ** 3) ** 2, (2 ** 3) ** 3)
    exit()
    print([i.lower() for i in "TURING"])
    exit()
    x = "abcdef"
    i = "a"
    while i in x[:-1]:
        print(i, end=" ")
    exit(0)
    def add(c, k):
        c.test = c.test + 1
        k = k + 1


    class Plus:
        def __init__(self):
            self.test = 0


    def main():
        p = Plus()
        index = 0

        for i in range(0, 25):
            add(p, index)

        print(p.test)
        print(index)
    main()

    def func1():
        x = 50
        return x


    func1()
    print(x)
    a = {40:"sjdg"}
    print(a)

    data = [10, 20, 30, 40, 50]
    data.pop()
    print(data)
    data.pop(2)
    print(data)
    exit(0)
    list1 = [1, 2, 6, 12]
    list2 = [12, 6, 2, 1]
    print(list1 == list2)
    print(set(list1) == set(list2))
    exit(0)



    class Developer(object):
        def __init__(self, skills):
            print(1)
            self.skills = skills

        def __add__(self, other):
            print(2)
            skills = self.skills + other.skills
            return Developer(skills)

        def __str__(self):
            print(3)
            return "Skills"


    A = Developer('NodeJS')
    B = Developer('Python')
    print("check")
    print(A + B)

    exit(0)
    listone = [1, 2, 3]
    listtwo = [4, 5, 6]
    listone.append(listtwo)
    print(listone)
    print(listone + listtwo)
    import re

    result = re.findall('Welcome to Turing', 'Welcome', 1)
    print(result)

    array1 = [1, 2, 3, 4, 5]
    array2 = array1
    array2[0] = 0
    print(array1)
    exit(0)

    array = ['Welcome', 'To', 'Turing']
    print("-".join(array))
    exit(0)
    class hello:

        def __init__(self, a='Welcome to '):
            self.a = a

        def welcome(self, x):
            print(self.a + x)


    h = hello()
    h.welcome('Turing')

    i = "Welcome"
    exit(0)
    def welcom(i):
        i = i + "skhd"
        return i
    welcom("check")
    print(i)

    #print('as {} sdsd {1} {2}'.format('qw1','qw2','qw3'))



    def listSkills(val, list=[]):
        list.append(val)
        return list


    list1 = listSkills('NodeJS')
    list2 = listSkills('Java', [])
    list3 = listSkills('ReactJS')
    print("%s" % list1)
    print("%s" % list2)
    print("%s" % list3)

    t = '%(a)s %(b)s %(c)s'
    print(t % dict(a='w', b='d',c='c'))

    a = 'abc'
    for i in range(len(a)):
        a[i].upper()
    print(a)

    z = set('abc')
    z.add('san')
    z.update(set(['p', 'q']))
    print(z)
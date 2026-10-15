from fastapi import APIRouter
from repositories.trialgpt_corpus_repo import get_all_regions
from repositories.compose_repo import get_patient_diseases


router = APIRouter()


@router.get("/api/trials/regions")
def get_regions():
    regions = get_all_regions()
    return {"regions": regions}




@router.get("/api/trials/diseases")
def get_diseases():
    diseases = get_patient_diseases()
    return {"diseases": diseases}
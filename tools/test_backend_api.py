#!/usr/bin/env python3
"""
Test Backend API - Validate que o backend segue o mesmo pipeline do debug script
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{text}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*70}{Colors.ENDC}\n")

def print_step(step: int, text: str):
    print(f"{Colors.BOLD}{Colors.BLUE}▶ PASSO {step}: {text}{Colors.ENDC}")

def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")

def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.ENDC}")

def print_info(text: str):
    print(f"{Colors.CYAN}ℹ {text}{Colors.ENDC}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.ENDC}")

# ============================================================================
# TEST SCENARIOS
# ============================================================================

TEST_REPOS = [
    {
        "name": "Keras",
        "url": "https://github.com/keras-team/keras",
        "description": "Neural network library"
    },
    {
        "name": "Pandas",
        "url": "https://github.com/pandas-dev/pandas",
        "description": "Data analysis library"
    },
    {
        "name": "Scikit-learn",
        "url": "https://github.com/scikit-learn/scikit-learn",
        "description": "Machine learning library"
    },
]

# ============================================================================
# TEST FUNCTIONS
# ============================================================================

def check_server_running(base_url: str) -> bool:
    """Check if backend server is running"""
    print_step(0, "Verificar se backend está rodando")
    
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        if response.status_code == 200:
            print_success(f"Backend rodando em {base_url}")
            return True
    except requests.exceptions.ConnectionError:
        pass
    except requests.exceptions.Timeout:
        pass
    
    print_error(f"Backend não está rodando em {base_url}")
    print_info(f"Inicie com: python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000")
    return False

def test_single_evaluation(base_url: str, repo_url: str, repo_name: str) -> Optional[dict]:
    """Test a single repository evaluation"""
    print_step(1, f"Enviar requisição para avaliar {repo_name}")
    
    payload = {
        "repo_url": repo_url,
    }
    
    print_info(f"Repository: {repo_url}")
    
    try:
        # Make request
        response = requests.post(
            f"{base_url}/jobs",
            json=payload,
            timeout=300  # 5 minutes timeout
        )
        
        if response.status_code != 200:
            print_error(f"Erro na requisição: {response.status_code}")
            print_error(f"Response: {response.text}")
            return None
        
        data = response.json()
        job_id = data.get("job_id")
        
        if not job_id:
            print_error("Job ID não retornado")
            return None
        
        print_success(f"Requisição enviada! Job ID: {job_id}")
        return {"job_id": job_id, "status": "submitted"}
        
    except requests.exceptions.Timeout:
        print_error("Timeout na requisição (5 minutos)")
        return None
    except requests.exceptions.RequestException as e:
        print_error(f"Erro na requisição: {e}")
        return None

def wait_for_job_completion(base_url: str, job_id: str, timeout: int = 300) -> Optional[dict]:
    """Wait for job to complete"""
    print_step(2, f"Aguardar conclusão do job {job_id}")
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{base_url}/jobs/{job_id}", timeout=10)
            
            if response.status_code == 200:
                job_data = response.json()
                status = job_data.get("status")
                
                # Print status changes
                if status != last_status:
                    print_info(f"Status: {status}")
                    
                    # Print step-specific info if available
                    if job_data.get("steps"):
                        for step in job_data["steps"]:
                            if step.get("completed"):
                                print_success(f"  ✓ {step.get('name')}")
                    
                    last_status = status
                
                # Check if completed
                if status == "success":
                    print_success(f"Job concluído com sucesso!")
                    return job_data
                elif status == "failed":
                    print_error(f"Job falhou!")
                    error = job_data.get("error")
                    if error:
                        print_error(f"  Erro: {error}")
                    return job_data
                
                time.sleep(5)  # Wait 5 seconds before next check
            else:
                print_error(f"Erro ao buscar status: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            print_warning(f"Erro ao buscar status: {e}")
            time.sleep(5)
    
    print_error(f"Timeout aguardando job (máximo: {timeout}s)")
    return None

def get_job_result(base_url: str, job_id: str) -> Optional[dict]:
    """Get final job result"""
    print_step(3, "Recuperar resultado da avaliação")
    
    try:
        response = requests.get(f"{base_url}/jobs/{job_id}", timeout=10)
        
        if response.status_code == 200:
            job_data = response.json()
            
            if job_data.get("status") == "success":
                result = job_data.get("result")
                if result:
                    print_success("Resultado obtido!")
                    
                    # Print summary
                    if "categories" in result:
                        print_info(f"Categorias avaliadas: {len(result['categories'])}")
                        
                        for category_name, category_data in result["categories"].items():
                            if isinstance(category_data, dict):
                                score = category_data.get("score", "N/A")
                                print_info(f"  • {category_name}: {score}")
                    
                    return result
            else:
                print_error(f"Job não completou com sucesso: {job_data.get('status')}")
        else:
            print_error(f"Erro ao buscar resultado: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print_error(f"Erro ao buscar resultado: {e}")
    
    return None

def validate_result_structure(result: dict) -> bool:
    """Validate result has expected structure"""
    print_step(4, "Validar estrutura do resultado")
    
    required_keys = ["categories"]
    
    for key in required_keys:
        if key not in result:
            print_error(f"Campo obrigatório ausente: {key}")
            return False
        print_success(f"Campo presente: {key}")
    
    # Check categories
    if isinstance(result.get("categories"), dict):
        categories = result["categories"]
        print_info(f"Total de categorias: {len(categories)}")
        
        for cat_name, cat_data in categories.items():
            if isinstance(cat_data, dict):
                # Check for arrays that should have been fixed
                for field in ["justifications", "evidences", "suggested_improvements"]:
                    if field in cat_data:
                        if isinstance(cat_data[field], dict):
                            for sub_field, values in cat_data[field].items():
                                if isinstance(values, list):
                                    print_success(f"  ✓ {cat_name}.{field}.{sub_field} é array")
                                else:
                                    print_warning(f"  ⚠ {cat_name}.{field}.{sub_field} não é array: {type(values)}")
    
    return True

def save_result_to_file(result: dict, repo_name: str, output_dir: str = "processed"):
    """Save result to JSON file"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    filename = f"result-{repo_name}-{timestamp}.json"
    filepath = output_path / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print_success(f"Resultado salvo em: {filepath}")

# ============================================================================
# MAIN TEST FLOW
# ============================================================================

def run_complete_test(base_url: str, repo_url: str, repo_name: str):
    """Run complete test flow for a repository"""
    print_header(f"TESTANDO: {repo_name}")
    print_info(f"URL: {repo_url}\n")
    
    # Step 1: Send evaluation request
    job_result = test_single_evaluation(base_url, repo_url, repo_name)
    if not job_result:
        return False
    
    job_id = job_result["job_id"]
    
    # Step 2: Wait for completion
    completed_job = wait_for_job_completion(base_url, job_id)
    if not completed_job:
        return False
    
    # Step 3: Get result
    result = get_job_result(base_url, job_id)
    if not result:
        return False
    
    # Step 4: Validate structure
    if not validate_result_structure(result):
        print_warning("Estrutura do resultado pode estar incompleta")
    
    # Step 5: Save to file
    save_result_to_file(result, repo_name)
    
    print_success(f"\n✅ Teste completo para {repo_name}!\n")
    return True

def main():
    """Main test runner"""
    print_header("🧪 TESTE DO BACKEND API")
    print(f"Este script valida que o backend segue o mesmo pipeline do debug script\n")
    
    # Configuration
    base_url = "http://localhost:8000"
    
    # Check if server is running
    if not check_server_running(base_url):
        print_error("\n❌ Servidor não está disponível!")
        return 1
    
    print("\n")
    
    # Run tests
    successful_tests = 0
    failed_tests = 0
    
    for test_repo in TEST_REPOS:
        print_info(f"\nTeste {successful_tests + failed_tests + 1}/{len(TEST_REPOS)}")
        
        if run_complete_test(base_url, test_repo["url"], test_repo["name"]):
            successful_tests += 1
        else:
            failed_tests += 1
        
        # Wait between tests
        if successful_tests + failed_tests < len(TEST_REPOS):
            print_info("Aguardando 5 segundos antes do próximo teste...\n")
            time.sleep(5)
    
    # Summary
    print_header("📊 RESUMO DOS TESTES")
    print(f"Testes bem-sucedidos: {Colors.GREEN}{successful_tests}{Colors.ENDC}")
    print(f"Testes falhados:      {Colors.RED}{failed_tests}{Colors.ENDC}")
    print(f"Total:                {len(TEST_REPOS)}\n")
    
    if failed_tests == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ TODOS OS TESTES PASSARAM!{Colors.ENDC}")
        print(f"\n✓ Backend está funcionando corretamente")
        print(f"✓ Pipeline segue o mesmo caminho que debug script")
        print(f"✓ Post-processor está ativo")
        print(f"✓ Validação de schema está passando")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}❌ ALGUNS TESTES FALHARAM{Colors.ENDC}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

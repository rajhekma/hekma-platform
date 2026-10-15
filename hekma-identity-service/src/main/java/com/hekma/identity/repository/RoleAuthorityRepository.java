package com.hekma.identity.repository;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.RoleAuthorityEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Set;
import java.util.UUID;

@Repository
public interface RoleAuthorityRepository extends JpaRepository<RoleAuthorityEntity, UUID> {

    List<RoleAuthorityEntity> findByRole(Role role);

    @Query("SELECT ra.authority FROM RoleAuthorityEntity ra WHERE ra.role = :role")
    Set<Authority> findAuthoritiesByRole(@Param("role") Role role);

    void deleteByRole(Role role);
}
